from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_config import db
from firebase_admin import firestore, auth as firebase_auth
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import uuid
import os
import hashlib
from functools import wraps
from datetime import datetime, timedelta, timezone
import jwt

# --- HELPERS FOR SYSTEM CLOSURES ---
def get_slots_in_range(range_str):
    ALL_TIMES = [
        "08:00 AM - 09:00 AM", "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM",
        "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM",
        "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM",
        "05:00 PM - 06:00 PM", "06:00 PM - 07:45 PM"
    ]
    if " - " not in range_str:
        return []
    parts = range_str.split(" - ")
    if len(parts) != 2:
        return []
    range_start, range_end = parts[0].strip(), parts[1].strip()
    
    start_idx = -1
    end_idx = -1
    for i, slot in enumerate(ALL_TIMES):
        s_parts = slot.split(" - ")
        if s_parts[0].strip() == range_start:
            start_idx = i
        if s_parts[1].strip() == range_end:
            end_idx = i
            
    if start_idx != -1 and end_idx != -1 and start_idx <= end_idx:
        return ALL_TIMES[start_idx:end_idx+1]
    return []


def merge_slots(slots_map):
    ALL_TIMES = [
        "08:00 AM - 09:00 AM", "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM",
        "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM",
        "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM",
        "05:00 PM - 06:00 PM", "06:00 PM - 07:45 PM"
    ]
    
    from collections import defaultdict
    reason_to_slots = defaultdict(list)
    for slot, reason in slots_map.items():
        reason_to_slots[reason].append(slot)
        
    merged_results = []
    for reason, slots in reason_to_slots.items():
        indices = sorted([ALL_TIMES.index(s) for s in slots if s in ALL_TIMES])
        if not indices:
            continue
        
        runs = []
        current_run = [indices[0]]
        for idx in indices[1:]:
            if idx == current_run[-1] + 1:
                current_run.append(idx)
            else:
                runs.append(current_run)
                current_run = [idx]
        runs.append(current_run)
        
        for run in runs:
            start_slot = ALL_TIMES[run[0]]
            end_slot = ALL_TIMES[run[-1]]
            start_time = start_slot.split(" - ")[0]
            end_time = end_slot.split(" - ")[1]
            merged_results.append({
                "time_slot": f"{start_time} - {end_time}",
                "reason": reason
            })
            
    return merged_results


def is_slot_blocked(date, time_slot):
    block_doc = db.collection("blocked_days").document(date).get()
    if block_doc.exists:
        doc_data = block_doc.to_dict()
        if doc_data.get("type", "full") == "full":
            return True, doc_data.get("reason", "Library Closed")
        elif doc_data.get("type") == "hours":
            slots_data = doc_data.get("slots", {})
            if isinstance(slots_data, list):
                if time_slot in slots_data:
                    return True, doc_data.get("reason", "Library Closed")
            elif isinstance(slots_data, dict):
                if time_slot in slots_data:
                    return True, slots_data[time_slot]
    return False, None



app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": ["*"]}},
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "DELETE", "OPTIONS"],
)

# --- CONFIGURATION ---
# (Note: ADMIN_PASSWORD is removed from here because it is now securely fetched from Firebase!)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "noreply.roombooking@nirmauni.ac.in"
SENDER_PASSWORD = "ogsvvjnrarucvmgh"

ADMIN_EMAIL = "noreply.roombooking@nirmauni.ac.in"
STAFF_EMAILS_COLLECTION = "Authorized_Staff"


def derive_jwt_secret():
    explicit = os.environ.get("JWT_SECRET")
    if explicit:
        return explicit

    firebase_credentials = os.environ.get("FIREBASE_CREDENTIALS")
    if firebase_credentials:
        return hashlib.sha256(firebase_credentials.encode("utf-8")).hexdigest()

    for path in ("serviceAccountKey.json", "/etc/secrets/serviceAccountKey.json"):
        if os.path.exists(path):
            with open(path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()

    return "dev-only-jwt-secret-change-me"


JWT_SECRET = derive_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 12


# --- HELPER: EMAIL FUNCTIONS ---
def send_confirmation_email(to_email, booking_data, token):
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = (
            f"Booking Confirmed: {booking_data['room_id']} - NIMA Knowledge Centre"
        )
        cancel_link = f"https://nima-roombooking-backend.vercel.app/cancel-via-email?token={token}"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd;">
            <h2 style="color: #27ae60;">Booking Confirmed!</h2>
            <p>Hello {booking_data['leader_name']},</p>
            <p>Your slot is reserved.</p>
            <p><strong>Room:</strong> {booking_data['room_id']}<br>
            <strong>Time:</strong> {booking_data['time_slot']}<br>
            <strong>Date:</strong> {booking_data['date']}</p>
            <br>
            <p>Thank you,</p>
            <p style="color: #D32F2F; font-weight: bold;">NIMA Knowledge Centre</p>
            <br>
            <a href="{cancel_link}" style="background: #c0392b; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px;">Cancel Booking</a>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Email Error: {e}")


def send_admin_cancellation_email(to_email, name, room, date, time):
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = "⚠️ Booking Cancelled - NIMA Knowledge Centre"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-top: 5px solid #c0392b;">
            <h2 style="color: #c0392b;">Booking Cancelled Successfully</h2>
            <p>Dear {name},</p>
            <p>As per your request (or Library Admin action), your discussion room booking has been cancelled successfully.</p>
            <div style="background: #f9f9f9; padding: 15px; margin: 15px 0;">
                <p><strong>Room:</strong> {room}</p><p><strong>Date:</strong> {date}</p><p><strong>Time:</strong> {time}</p>
            </div>
            <p>Thanks,</p>
            <p style="color: #D32F2F; font-weight: bold;">NIMA Knowledge Centre</p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Email Error: {e}")


# --- HELPER: SECURE FIREBASE PASSWORDS ---
def get_system_password(user_type):
    try:
        doc = db.collection("System_Settings").document("credentials").get()
        if doc.exists:
            return doc.to_dict().get(f"{user_type}_password", f"{user_type}123")
        return f"{user_type}123"  # Default fallback
    except Exception:
        return f"{user_type}123"


def normalize_email(email):
    return (email or "").strip().lower()


def is_valid_university_email(email):
    return normalize_email(email).endswith("@nirmauni.ac.in")


def is_staff_email(email):
    email = normalize_email(email)
    if not email:
        return False
    return db.collection(STAFF_EMAILS_COLLECTION).document(email).get().exists


def resolve_role(email):
    email = normalize_email(email)
    if email == ADMIN_EMAIL:
        return {"role": "admin"}

    staff_doc = db.collection(STAFF_EMAILS_COLLECTION).document(email).get()
    if staff_doc.exists:
        return {"role": "staff"}

    if is_valid_university_email(email):
        return {"role": "student"}

    return None


def issue_token(role, email=None):
    now = datetime.now(timezone.utc)
    payload = {
        "role": role,
        "email": normalize_email(email),
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


def require_auth(allowed_roles=None):
    allowed_roles = set(allowed_roles or [])

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = get_bearer_token()
            if not token:
                return jsonify({"status": "error", "message": "Unauthorized"}), 401

            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            except jwt.ExpiredSignatureError:
                return jsonify({"status": "error", "message": "Session expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"status": "error", "message": "Invalid token"}), 401

            role = payload.get("role")
            if allowed_roles and role not in allowed_roles:
                return jsonify({"status": "error", "message": "Forbidden"}), 403

            request.jwt_payload = payload
            return fn(*args, **kwargs)

        return wrapper

    return decorator


# --- API ROUTES ---


@app.route("/confirm-booking", methods=["POST"])
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
        if data.get("leader_name") != "ADMIN BLOCK":
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

        if data.get("email") and data["leader_name"] != "ADMIN BLOCK":
            send_confirmation_email(data["email"], data, cancel_token)

        return jsonify({"status": "success", "message": "Booking Confirmed!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/cancel-booking", methods=["POST"])
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
        user_email = booking_info.get("details", {}).get("email")
        leader_name = booking_info.get("details", {}).get("leader_name")

        slot_ref.delete()

        if user_email and leader_name != "ADMIN BLOCK":
            send_admin_cancellation_email(
                user_email,
                leader_name,
                room_id,
                date,
                time_slot,
            )

        return jsonify({"status": "success", "message": "Cancelled & Email Sent"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/cancel-via-email", methods=["GET"])
def cancel_via_email():
    try:
        token = request.args.get("token")
        if not token:
            return "Invalid Link", 400
        docs = db.collection("daily_slots").where("cancel_token", "==", token).stream()
        found = False
        for doc in docs:
            booking_info = doc.to_dict()
            user_email = booking_info.get("details", {}).get("email")
            leader_name = booking_info.get("details", {}).get("leader_name")
            room = booking_info.get("room_id")
            date = booking_info.get("date")
            time = booking_info.get("time_slot")

            doc.reference.delete()
            found = True

            if user_email:
                send_admin_cancellation_email(user_email, leader_name, room, date, time)

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


@app.route("/auth/login", methods=["POST"])
def auth_login():
    try:
        id_token = request.json.get("id_token")
        if not id_token:
            return jsonify({"status": "error", "message": "ID token required"}), 400

        decoded = firebase_auth.verify_id_token(id_token)
        email = normalize_email(decoded.get("email"))
        role_info = resolve_role(email)
        if not role_info:
            return jsonify({"status": "error", "message": "Unauthorized email"}), 403

        role = role_info.get("role")
        token = issue_token(role, email)
        return (
            jsonify(
                {
                    "status": "success",
                    "token": token,
                    "role": role,
                    "email": email,
                    "name": decoded.get("name") or decoded.get("email", ""),
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 401


@app.route("/admin/staff-emails", methods=["GET"])
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


@app.route("/admin/staff-emails", methods=["POST"])
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


@app.route("/admin/staff-emails", methods=["DELETE"])
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


@app.route("/admin/block-day", methods=["POST"])
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

            # Delete the booking from Firestore
            doc.reference.delete()

            # Send email only if it is a student booking
            if leader_name != "ADMIN BLOCK" and leader_name != "SYSTEM BLOCK":
                user_email = details.get("email")
                if user_email:
                    send_admin_cancellation_email(
                        user_email,
                        leader_name,
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


@app.route("/admin/block-slots", methods=["POST"])
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

                # Delete the booking
                doc.reference.delete()

                # Send cancellation email for actual student bookings
                if leader_name != "ADMIN BLOCK" and leader_name != "SYSTEM BLOCK":
                    user_email = details.get("email")
                    if user_email:
                        send_admin_cancellation_email(
                            user_email,
                            leader_name,
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


@app.route("/admin/active-closures", methods=["GET"])
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


@app.route("/admin/reopen-closure", methods=["POST"])
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


@app.route("/get-bookings", methods=["GET"])
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


@app.route("/my-bookings", methods=["GET"])
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


@app.route("/admin/all-bookings", methods=["GET"])
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
                "leader": details.get("leader_name", "Unknown"),
                "roll_no": details.get("leader_roll_no", "N/A"),
                "institute": details.get("institute", "N/A"),
                "email": details.get("email", "N/A"),
                "contact_no": details.get("contact_no", "N/A"),
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
                "contact_no": "N/A",
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
                    "contact_no": "N/A",
                    "programme": "N/A",
                    "purpose": f"Library Closed — {m['reason']}",
                    "members": []
                })

    return jsonify({"bookings": data}), 200


# ==========================================
# 🔒 SECURE LOGIN & PASSWORD MANAGEMENT APIs
# ==========================================


@app.route("/admin-login", methods=["POST"])
def admin_login():
    req_pass = request.json.get("password")
    if req_pass == get_system_password("admin"):
        return (
            jsonify(
                {
                    "status": "success",
                    "token": issue_token("admin", ADMIN_EMAIL),
                    "role": "admin",
                }
            ),
            200,
        )
    return jsonify({"status": "error", "message": "Invalid password"}), 401


# --- NEW ROUTE ADDED HERE ---
@app.route("/staff-login", methods=["POST"])
def staff_login():
    req_pass = request.json.get("password")
    if req_pass == get_system_password("staff"):
        return (
            jsonify(
                {"status": "success", "token": issue_token("staff"), "role": "staff"}
            ),
            200,
        )
    return jsonify({"status": "error", "message": "Invalid password"}), 401


# -----------------------------


@app.route("/auth/verify", methods=["GET"])
def verify_auth():
    token = get_bearer_token()
    if not token:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return (
            jsonify(
                {
                    "status": "success",
                    "role": payload.get("role"),
                    "email": payload.get("email"),
                }
            ),
            200,
        )
    except jwt.ExpiredSignatureError:
        return jsonify({"status": "error", "message": "Session expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"status": "error", "message": "Invalid token"}), 401


@app.route("/admin/change-password", methods=["POST"])
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


@app.route("/admin/change-staff-password", methods=["POST"])
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
# 🚪 NEW FIREBASE ROOM MANAGEMENT APIs
# ==========================================


@app.route("/get-rooms", methods=["GET"])
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


@app.route("/admin/add-room", methods=["POST"])
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


@app.route("/admin/delete-room", methods=["POST"])
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
