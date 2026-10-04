import uuid

from firebase_admin import firestore
from flask import Blueprint, jsonify, request

from ..email_service import send_admin_cancellation_email, send_confirmation_email
from ..firebase_config import db
from ..slots import is_slot_blocked

bookings_bp = Blueprint("bookings", __name__)


@bookings_bp.route("/confirm-booking", methods=["POST"])
def confirm_booking():
    try:
        data = request.json
        date = data.get("date")
        time_slot = data.get("time_slot")

        # Check server-side closure validation
        blocked, reason = is_slot_blocked(date, time_slot)
        if blocked:
            return jsonify({"status": "error", "message": f"Slot is unavailable: {reason}"}), 400

        # 🛑 RULE 1: DUPLICATE BOOKING CHECK (Same roll no, same day)
        if data.get("leader_roll_no") and data.get("leader_name") != "ADMIN BLOCK":
            existing_bookings = (
                db.collection("daily_slots")
                .where("date", "==", data["date"])
                .where("details.leader_roll_no", "==", data["leader_roll_no"])
                .stream()
            )

            for _ in existing_bookings:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Duplicate Booking: You have already booked a room for this date. Only 1 booking per day is allowed.",
                        }
                    ),
                    400,
                )

        slot_id = f"{data['room_id']}_{data['date']}_{data['time_slot']}"
        slot_ref = db.collection("daily_slots").document(slot_id)
        cancel_token = str(uuid.uuid4())

        transaction = db.transaction()

        @firestore.transactional
        def run_txn(transaction, slot_ref, booking_data, token):
            snapshot = slot_ref.get(transaction=transaction)
            if snapshot.exists and snapshot.get("status") == "booked":
                raise Exception("Slot already booked")
            transaction.set(
                slot_ref,
                {
                    "status": "booked",
                    "date": booking_data.get("date"),
                    "time_slot": booking_data.get("time_slot"),
                    "room_id": booking_data.get("room_id"),
                    "cancel_token": token,
                    "details": booking_data,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )

        run_txn(transaction, slot_ref, data, cancel_token)

        if data.get("email") and data.get("leader_name") != "ADMIN BLOCK":
            send_confirmation_email(data["email"], data, cancel_token)

        return jsonify({"status": "success", "message": "Booking Confirmed!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@bookings_bp.route("/cancel-booking", methods=["POST"])
def cancel_booking():
    try:
        data = request.json
        room_id = data.get("room_id")
        date = data.get("date")
        time_slot = data.get("time_slot")

        if room_id == "SYSTEM":
            return jsonify({"status": "error", "message": "Use the admin reopen endpoint for library closures"}), 400

        slot_id = f"{room_id}_{date}_{time_slot}"
        slot_ref = db.collection("daily_slots").document(slot_id)
        doc = slot_ref.get()
        if not doc.exists:
            return jsonify({"status": "error", "message": "Booking not found"}), 404
        booking_info = doc.to_dict()
        details = booking_info.get("details", {})
        user_email = details.get("email")
        leader_roll = details.get("leader_roll_no", "Student")
        leader_name = details.get("leader_name", "")

        slot_ref.delete()

        if user_email and leader_name != "ADMIN BLOCK":
            send_admin_cancellation_email(
                user_email,
                leader_roll,
                room_id,
                date,
                time_slot,
            )

        return jsonify({"status": "success", "message": "Cancelled & Email Sent"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@bookings_bp.route("/cancel-via-email", methods=["GET"])
def cancel_via_email():
    try:
        token = request.args.get("token")
        if not token:
            return "Invalid Link", 400
        docs = db.collection("daily_slots").where("cancel_token", "==", token).stream()
        found = False
        for doc in docs:
            booking_info = doc.to_dict()
            details = booking_info.get("details", {})
            user_email = details.get("email")
            leader_roll = details.get("leader_roll_no", "Student")
            room = booking_info.get("room_id")
            date = booking_info.get("date")
            time = booking_info.get("time_slot")

            doc.reference.delete()
            found = True

            if user_email:
                send_admin_cancellation_email(user_email, leader_roll, room, date, time)

        if found:
            return (
                "<h1 style='color:green; text-align:center;'>Booking Cancelled Successfully</h1>",
                200,
            )
        return (
            "<h1 style='text-align:center;'>Booking not found or already cancelled.</h1>",
            404,
        )
    except Exception as e:
        return f"Error: {str(e)}", 500


@bookings_bp.route("/get-bookings", methods=["GET"])
def get_bookings():
    try:
        date = request.args.get("date")
        block_doc = db.collection("blocked_days").document(date).get()
        blocked_slots = []
        if block_doc.exists:
            doc_data = block_doc.to_dict()
            if doc_data.get("type", "full") == "full":
                return (
                    jsonify(
                        {
                            "status": "closed",
                            "reason": doc_data.get("reason", "Closed"),
                        }
                    ),
                    200,
                )
            elif doc_data.get("type") == "hours":
                slots_data = doc_data.get("slots", {})
                if isinstance(slots_data, list):
                    blocked_slots = slots_data
                elif isinstance(slots_data, dict):
                    blocked_slots = list(slots_data.keys())

        docs = db.collection("daily_slots").where("date", "==", date).stream()
        bookings = [
            {
                "time_slot": d.to_dict().get("time_slot"),
                "room_id": d.to_dict().get("room_id"),
            }
            for d in docs
        ]
        return jsonify({"bookings": bookings, "blocked_slots": blocked_slots}), 200
    except Exception as e:
        return jsonify({"status": "error"}), 400


@bookings_bp.route("/my-bookings", methods=["GET"])
def my_bookings():
    try:
        roll_no = request.args.get("roll_no")
        email = request.args.get("email")

        if email:
            docs = (
                db.collection("daily_slots")
                .where("details.email", "==", email)
                .stream()
            )
        elif roll_no:
            docs = (
                db.collection("daily_slots")
                .where("details.leader_roll_no", "==", roll_no)
                .stream()
            )
        else:
            return (
                jsonify({"status": "error", "message": "Email or Roll No required"}),
                400,
            )

        bookings = [
            {
                "room_id": d.to_dict().get("room_id"),
                "date": d.to_dict().get("date"),
                "time_slot": d.to_dict().get("time_slot"),
            }
            for d in docs
        ]
        return jsonify({"status": "success", "bookings": bookings}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
