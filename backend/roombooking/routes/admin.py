from firebase_admin import firestore
from flask import Blueprint, jsonify, request

from ..config import ADMIN_EMAIL, STAFF_EMAILS_COLLECTION
from ..email_service import send_admin_cancellation_email
from ..firebase_config import db
from ..security import (
    is_valid_university_email,
    normalize_email,
    require_auth,
)
from ..slots import get_slots_in_range, merge_slots

admin_bp = Blueprint("admin", __name__)


# ==========================================
# 👤 STAFF EMAIL MANAGEMENT
# ==========================================


@admin_bp.route("/admin/staff-emails", methods=["GET"])
@require_auth(["admin"])
def list_staff_emails():
    try:
        docs = db.collection(STAFF_EMAILS_COLLECTION).stream()
        emails = sorted(
            [
                normalize_email(doc.to_dict().get("email") or doc.id)
                for doc in docs
                if normalize_email(doc.to_dict().get("email") or doc.id)
            ]
        )
        return jsonify({"status": "success", "staff_emails": emails}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/admin/staff-emails", methods=["POST"])
@require_auth(["admin"])
def add_staff_email():
    try:
        email = normalize_email(request.json.get("email"))
        if not email or not is_valid_university_email(email):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Enter a valid @nirmauni.ac.in email",
                    }
                ),
                400,
            )

        if email == ADMIN_EMAIL:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Admin email cannot be added as staff",
                    }
                ),
                400,
            )

        db.collection(STAFF_EMAILS_COLLECTION).document(email).set(
            {"email": email, "added_at": firestore.SERVER_TIMESTAMP}, merge=True
        )
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/admin/staff-emails", methods=["DELETE"])
@require_auth(["admin"])
def delete_staff_email():
    try:
        email = normalize_email(request.json.get("email"))
        if not email:
            return jsonify({"status": "error", "message": "Email required"}), 400
        db.collection(STAFF_EMAILS_COLLECTION).document(email).delete()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 🚫 LIBRARY CLOSURES
# ==========================================


@admin_bp.route("/admin/block-day", methods=["POST"])
@require_auth(["admin"])
def block_day():
    try:
        data = request.json
        date = data.get("date")
        reason = data.get("reason", "Closed")

        # Query and cancel all existing student bookings on this date
        bookings_ref = db.collection("daily_slots").where("date", "==", date).stream()
        for doc in bookings_ref:
            booking_info = doc.to_dict()
            details = booking_info.get("details", {})
            leader_name = details.get("leader_name", "")
            leader_roll = details.get("leader_roll_no", "Student")

            # Delete the booking from Firestore
            doc.reference.delete()

            # Send email only if it is a student booking
            if leader_name != "ADMIN BLOCK" and leader_name != "SYSTEM BLOCK":
                user_email = details.get("email")
                if user_email:
                    send_admin_cancellation_email(
                        user_email,
                        leader_roll,
                        booking_info.get("room_id"),
                        date,
                        booking_info.get("time_slot")
                    )

        # Save the full day block in Firestore
        db.collection("blocked_days").document(date).set(
            {"type": "full", "reason": reason, "blocked_by": "admin"}
        )
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@admin_bp.route("/admin/block-slots", methods=["POST"])
@require_auth(["admin"])
def block_slots():
    try:
        data = request.json
        date = data["date"]
        slots = data["slots"]
        reason = data.get("reason", "Closed")

        # Query and cancel existing student bookings in daily_slots for these slots
        bookings_ref = db.collection("daily_slots").where("date", "==", date).stream()
        for doc in bookings_ref:
            booking_info = doc.to_dict()
            time_slot = booking_info.get("time_slot")
            if time_slot in slots:
                details = booking_info.get("details", {})
                leader_name = details.get("leader_name", "")
                leader_roll = details.get("leader_roll_no", "Student")

                # Delete the booking
                doc.reference.delete()

                # Send cancellation email for actual student bookings
                if leader_name != "ADMIN BLOCK" and leader_name != "SYSTEM BLOCK":
                    user_email = details.get("email")
                    if user_email:
                        send_admin_cancellation_email(
                            user_email,
                            leader_roll,
                            booking_info.get("room_id"),
                            date,
                            time_slot
                        )

        # Save the partial hours block in blocked_days (merging if document exists)
        block_ref = db.collection("blocked_days").document(date)
        block_doc = block_ref.get()

        existing_slots = {}
        if block_doc.exists:
            doc_data = block_doc.to_dict()
            if doc_data.get("type", "full") == "full":
                # Already fully closed, no need to merge slots
                return jsonify({"status": "success"}), 200

            existing_slots_raw = doc_data.get("slots", {})
            if isinstance(existing_slots_raw, list):
                existing_slots = {s: doc_data.get("reason", "Closed") for s in existing_slots_raw}
            elif isinstance(existing_slots_raw, dict):
                existing_slots = existing_slots_raw

        # Merge new slots into slots map
        for slot in slots:
            existing_slots[slot] = reason

        block_ref.set({
            "type": "hours",
            "reason": reason,
            "blocked_by": "admin",
            "slots": existing_slots
        })

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@admin_bp.route("/admin/active-closures", methods=["GET"])
@require_auth(["admin"])
def active_closures():
    """Return each currently active library closure for the admin dashboard."""
    try:
        closures = []
        for closure_doc in db.collection("blocked_days").stream():
            closure_data = closure_doc.to_dict()
            date = closure_doc.id
            closure_type = closure_data.get("type", "full")

            if closure_type == "full":
                closures.append({
                    "date": date,
                    "type": "full",
                    "time_slot": "All Day",
                    "reason": closure_data.get("reason", "Library Closed"),
                })
                continue

            if closure_type == "hours":
                slots_data = closure_data.get("slots", {})
                if isinstance(slots_data, list):
                    slots_map = {slot: closure_data.get("reason", "Library Closed") for slot in slots_data}
                elif isinstance(slots_data, dict):
                    slots_map = slots_data
                else:
                    slots_map = {}

                for merged_closure in merge_slots(slots_map):
                    closures.append({
                        "date": date,
                        "type": "hours",
                        "time_slot": merged_closure["time_slot"],
                        "slots": get_slots_in_range(merged_closure["time_slot"]),
                        "reason": merged_closure["reason"],
                    })

        closures.sort(key=lambda closure: (closure["date"], closure["time_slot"]))
        return jsonify({"status": "success", "closures": closures}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/admin/reopen-closure", methods=["POST"])
@require_auth(["admin"])
def reopen_closure():
    """Remove an active closure without restoring cancelled bookings or sending email."""
    try:
        data = request.get_json(silent=True) or {}
        date = data.get("date")
        closure_type = data.get("type")
        if not date or closure_type not in {"full", "hours"}:
            return jsonify({"status": "error", "message": "Date and closure type are required"}), 400

        block_ref = db.collection("blocked_days").document(date)
        block_doc = block_ref.get()
        if not block_doc.exists:
            return jsonify({"status": "error", "message": "Closure not found"}), 404

        block_data = block_doc.to_dict()
        if block_data.get("type", "full") != closure_type:
            return jsonify({"status": "error", "message": "Closure type no longer matches"}), 409

        if closure_type == "full":
            block_ref.delete()
            return jsonify({"status": "success", "message": "Full-day closure reopened"}), 200

        slots_to_reopen = data.get("slots")
        if not isinstance(slots_to_reopen, list) or not slots_to_reopen:
            return jsonify({"status": "error", "message": "At least one time slot is required"}), 400

        existing_slots_raw = block_data.get("slots", {})
        if isinstance(existing_slots_raw, list):
            existing_slots = {slot: block_data.get("reason", "Library Closed") for slot in existing_slots_raw}
        elif isinstance(existing_slots_raw, dict):
            existing_slots = existing_slots_raw
        else:
            existing_slots = {}

        slots_to_reopen = set(slots_to_reopen)
        if not any(slot in existing_slots for slot in slots_to_reopen):
            return jsonify({"status": "error", "message": "Selected time slots are not closed"}), 404

        remaining_slots = {
            slot: reason for slot, reason in existing_slots.items() if slot not in slots_to_reopen
        }
        if remaining_slots:
            block_ref.update({"slots": remaining_slots})
        else:
            block_ref.delete()

        return jsonify({"status": "success", "message": "Selected hours reopened"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 📋 BOOKINGS OVERVIEW
# ==========================================


@admin_bp.route("/admin/all-bookings", methods=["GET"])
@require_auth(["admin", "staff"])
def all_bookings():
    # 1. Fetch student bookings
    docs = db.collection("daily_slots").stream()
    data = []
    for doc in docs:
        d = doc.to_dict()
        details = d.get("details", {})
        data.append(
            {
                "room_id": d.get("room_id"),
                "date": d.get("date"),
                "time_slot": d.get("time_slot"),
                "roll_no": details.get("leader_roll_no", "N/A"),
                "institute": details.get("institute", "N/A"),
                "email": details.get("email", "N/A"),
                "programme": details.get("programme", "N/A"),
                "purpose": details.get("purpose", "N/A"),
                "members": details.get("members", []),
            }
        )

    # 2. Fetch closure blocks
    closures_ref = db.collection("blocked_days").stream()
    for closure_doc in closures_ref:
        c_data = closure_doc.to_dict()
        date = closure_doc.id
        c_type = c_data.get("type", "full")
        reason = c_data.get("reason", "Library Closed")

        if c_type == "full":
            data.append({
                "room_id": "SYSTEM",
                "date": date,
                "time_slot": "All Day",
                "leader": "SYSTEM BLOCK",
                "roll_no": "—",
                "institute": "N/A",
                "email": "N/A",
                "programme": "N/A",
                "purpose": f"Library Closed — {reason}",
                "members": []
            })
        elif c_type == "hours":
            slots_data = c_data.get("slots", {})
            slots_map = {}
            if isinstance(slots_data, list):
                slots_map = {s: reason for s in slots_data}
            elif isinstance(slots_data, dict):
                slots_map = slots_data

            merged = merge_slots(slots_map)
            for m in merged:
                data.append({
                    "room_id": "SYSTEM",
                    "date": date,
                    "time_slot": m["time_slot"],
                    "leader": "SYSTEM BLOCK",
                    "roll_no": "—",
                    "institute": "N/A",
                    "email": "N/A",
                    "programme": "N/A",
                    "purpose": f"Library Closed — {m['reason']}",
                    "members": []
                })

    return jsonify({"bookings": data}), 200


# ==========================================
# 🔒 SECURE PASSWORD MANAGEMENT
# ==========================================


@admin_bp.route("/admin/change-password", methods=["POST"])
@require_auth(["admin"])
def change_admin_password():
    try:
        new_pass = request.json.get("new_password")
        if not new_pass:
            return jsonify({"status": "error", "message": "Password required"}), 400
        # Save to Firebase permanently
        db.collection("System_Settings").document("credentials").set(
            {"admin_password": new_pass}, merge=True
        )
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error"}), 500


@admin_bp.route("/admin/change-staff-password", methods=["POST"])
@require_auth(["admin"])
def change_staff_password():
    try:
        new_pass = request.json.get("new_password")
        if not new_pass:
            return jsonify({"status": "error", "message": "Password required"}), 400
        # Save to Firebase permanently
        db.collection("System_Settings").document("credentials").set(
            {"staff_password": new_pass}, merge=True
        )
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error"}), 500


# ==========================================
# 🚪 FIREBASE ROOM MANAGEMENT
# ==========================================


@admin_bp.route("/get-rooms", methods=["GET"])
def get_rooms():
    try:
        docs = db.collection("Library_Rooms").stream()
        rooms = [doc.to_dict().get("room_name") for doc in docs]

        # Auto-create the database if it is empty!
        if len(rooms) == 0:
            default_rooms = [
                "Room 501",
                "Room 502",
                "Room 503",
                "Room 504",
                "Room 505",
                "Room 506",
                "Room 507",
                "Room 601",
                "Room 602",
                "Room 701",
                "Room 702",
                "Room 801",
                "Room 802",
            ]
            batch = db.batch()
            for r in default_rooms:
                doc_ref = db.collection("Library_Rooms").document()
                batch.set(doc_ref, {"room_name": r})
            batch.commit()
            rooms = default_rooms

        rooms.sort()
        return jsonify({"status": "success", "rooms": rooms}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/admin/add-room", methods=["POST"])
@require_auth(["admin"])
def add_room():
    try:
        room_name = request.json.get("room_name")
        if not room_name or not room_name.startswith("Room "):
            return (
                jsonify({"status": "error", "message": "Must start with 'Room '"}),
                400,
            )

        # Check for duplicates
        docs = (
            db.collection("Library_Rooms").where("room_name", "==", room_name).stream()
        )
        if any(docs):
            return jsonify({"status": "error", "message": "Room already exists"}), 400

        db.collection("Library_Rooms").add({"room_name": room_name})
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error"}), 500


@admin_bp.route("/admin/delete-room", methods=["POST"])
@require_auth(["admin"])
def delete_room():
    try:
        room_name = request.json.get("room_name")
        if not room_name:
            return jsonify({"status": "error"}), 400

        docs = (
            db.collection("Library_Rooms").where("room_name", "==", room_name).stream()
        )
        deleted = False

        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            deleted = True

        if not deleted:
            return jsonify({"status": "error", "message": "Room not found"}), 404

        batch.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error"}), 500
