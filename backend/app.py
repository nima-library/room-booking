from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_config import db 
from firebase_admin import firestore
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import uuid

app = Flask(__name__)
CORS(app) 

# --- CONFIGURATION ---
# (Note: ADMIN_PASSWORD is removed from here because it is now securely fetched from Firebase!)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "noreply.roombooking@nirmauni.ac.in"  
SENDER_PASSWORD = "rgnwarylovvaxijz" 

# --- HELPER: EMAIL FUNCTIONS ---
def send_confirmation_email(to_email, booking_data, token):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Booking Confirmed: {booking_data['room_id']} - NIMA Knowledge Centre"
        cancel_link = f"https://nima-backend.vercel.app/cancel-via-email?token={token}"
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
        msg.attach(MIMEText(html_body, 'html'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e: print(f"Email Error: {e}")

def send_admin_cancellation_email(to_email, name, room, date, time):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = "⚠️ Booking Cancelled - NIMA Knowledge Centre"
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
        msg.attach(MIMEText(html_body, 'html'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e: print(f"Email Error: {e}")

# --- HELPER: SECURE FIREBASE PASSWORDS ---
def get_system_password(user_type):
    try:
        doc = db.collection('System_Settings').document('credentials').get()
        if doc.exists:
            return doc.to_dict().get(f'{user_type}_password', f'{user_type}123')
        return f'{user_type}123' # Default fallback
    except Exception:
        return f'{user_type}123'

# --- API ROUTES ---

@app.route('/confirm-booking', methods=['POST'])
def confirm_booking():
    try:
        data = request.json
        
        # 🛑 RULE 1: DUPLICATE BOOKING CHECK (Same roll no, same day)
        if data['leader_name'] != "ADMIN BLOCK":
            existing_bookings = db.collection('daily_slots')\
                .where('date', '==', data['date'])\
                .where('details.leader_roll_no', '==', data['leader_roll_no']).stream()
            
            for _ in existing_bookings:
                return jsonify({"status": "error", "message": "Duplicate Booking: You have already booked a room for this date. Only 1 booking per day is allowed."}), 400

        slot_id = f"{data['room_id']}_{data['date']}_{data['time_slot']}"
        slot_ref = db.collection('daily_slots').document(slot_id)
        cancel_token = str(uuid.uuid4())

        transaction = db.transaction()
        @firestore.transactional
        def run_txn(transaction, slot_ref, booking_data, token):
            snapshot = slot_ref.get(transaction=transaction)
            if snapshot.exists and snapshot.get('status') == 'booked':
                raise Exception("Slot already booked")
            transaction.set(slot_ref, {
                'status': 'booked',
                'date': booking_data.get('date'),          
                'time_slot': booking_data.get('time_slot'),
                'room_id': booking_data.get('room_id'),
                'cancel_token': token,
                'details': booking_data,
                'timestamp': firestore.SERVER_TIMESTAMP
            }, merge=True)
            
        run_txn(transaction, slot_ref, data, cancel_token)

        if data.get('email') and data['leader_name'] != "ADMIN BLOCK":
            send_confirmation_email(data['email'], data, cancel_token)

        return jsonify({"status": "success", "message": "Booking Confirmed!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/cancel-booking', methods=['POST'])
def cancel_booking():
    try:
        data = request.json
        slot_id = f"{data['room_id']}_{data['date']}_{data['time_slot']}"
        slot_ref = db.collection('daily_slots').document(slot_id)
        doc = slot_ref.get()
        if not doc.exists: return jsonify({"status": "error", "message": "Booking not found"}), 404
        booking_info = doc.to_dict()
        user_email = booking_info.get('details', {}).get('email')
        leader_name = booking_info.get('details', {}).get('leader_name')

        slot_ref.delete()

        if user_email and leader_name != "ADMIN BLOCK":
            send_admin_cancellation_email(user_email, leader_name, data['room_id'], data['date'], data['time_slot'])

        return jsonify({"status": "success", "message": "Cancelled & Email Sent"}), 200
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/cancel-via-email', methods=['GET'])
def cancel_via_email():
    try:
        token = request.args.get('token')
        if not token: return "Invalid Link", 400
        docs = db.collection('daily_slots').where('cancel_token', '==', token).stream()
        found = False
        for doc in docs:
            booking_info = doc.to_dict()
            user_email = booking_info.get('details', {}).get('email')
            leader_name = booking_info.get('details', {}).get('leader_name')
            room = booking_info.get('room_id')
            date = booking_info.get('date')
            time = booking_info.get('time_slot')
            
            doc.reference.delete()
            found = True
            
            if user_email:
                 send_admin_cancellation_email(user_email, leader_name, room, date, time)
                 
        if found: return "<h1 style='color:green; text-align:center;'>Booking Cancelled Successfully</h1>", 200
        return "<h1 style='text-align:center;'>Booking not found or already cancelled.</h1>", 404
    except Exception as e: return f"Error: {str(e)}", 500

@app.route('/admin/block-day', methods=['POST'])
def block_day():
    try:
        data = request.json
        db.collection('blocked_days').document(data.get('date')).set({'reason': data.get('reason', 'Closed'), 'blocked_by': 'admin'})
        return jsonify({"status": "success"}), 200
    except Exception as e: return jsonify({"status": "error"}), 400

@app.route('/admin/block-slots', methods=['POST'])
def block_slots():
    try:
        data = request.json
        date = data['date']
        slots = data['slots'] 
        rooms = data['rooms'] 
        
        batch = db.batch()
        for slot in slots:
            for room in rooms:
                slot_id = f"{room}_{date}_{slot}"
                ref = db.collection('daily_slots').document(slot_id)
                batch.set(ref, {
                    'status': 'booked',
                    'date': date,
                    'time_slot': slot,
                    'room_id': room,
                    'details': {'leader_name': 'ADMIN BLOCK', 'purpose': 'Library Closed', 'leader_roll_no': 'N/A'}
                }, merge=True)
        batch.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/get-bookings', methods=['GET'])
def get_bookings():
    try:
        date = request.args.get('date')
        block_doc = db.collection('blocked_days').document(date).get()
        if block_doc.exists: return jsonify({"status": "closed", "reason": block_doc.to_dict().get('reason', "Closed")}), 200

        docs = db.collection('daily_slots').where('date', '==', date).stream()
        bookings = [{"time_slot": d.to_dict().get('time_slot'), "room_id": d.to_dict().get('room_id')} for d in docs]
        return jsonify({"bookings": bookings}), 200
    except Exception as e: return jsonify({"status": "error"}), 400

@app.route('/my-bookings', methods=['GET'])
def my_bookings():
    try:
        roll_no = request.args.get('roll_no')
        email = request.args.get('email')

        if email:
            docs = db.collection('daily_slots').where('details.email', '==', email).stream()
        elif roll_no:
            docs = db.collection('daily_slots').where('details.leader_roll_no', '==', roll_no).stream()
        else:
            return jsonify({"status": "error", "message": "Email or Roll No required"}), 400

        bookings = [{"room_id": d.to_dict().get('room_id'), "date": d.to_dict().get('date'), "time_slot": d.to_dict().get('time_slot')} for d in docs]
        return jsonify({"status": "success", "bookings": bookings}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/all-bookings', methods=['GET'])
def all_bookings():
    docs = db.collection('daily_slots').stream()
    data = []
    for doc in docs:
        d = doc.to_dict()
        details = d.get('details', {})
        data.append({
            "room_id": d.get('room_id'), 
            "date": d.get('date'), 
            "time_slot": d.get('time_slot'), 
            "leader": details.get('leader_name', 'Unknown'), 
            "roll_no": details.get('leader_roll_no', 'N/A'),
            "institute": details.get('institute', 'N/A'),
            "email": details.get('email', 'N/A'),
            "contact_no": details.get('contact_no', 'N/A'),
            "programme": details.get('programme', 'N/A'),
            "purpose": details.get('purpose', 'N/A'),
            "members": details.get('members', []) # 🚀 Added this line!
        })
    return jsonify({"bookings": data}), 200

# ==========================================
# 🔒 SECURE LOGIN & PASSWORD MANAGEMENT APIs
# ==========================================

@app.route('/admin-login', methods=['POST'])
def admin_login():
    req_pass = request.json.get('password')
    if req_pass == get_system_password('admin'): 
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "Invalid password"}), 401

# --- NEW ROUTE ADDED HERE ---
@app.route('/staff-login', methods=['POST'])
def staff_login():
    req_pass = request.json.get('password')
    if req_pass == get_system_password('staff'): 
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "Invalid password"}), 401
# -----------------------------

@app.route('/admin/change-password', methods=['POST'])
def change_admin_password():
    try:
        new_pass = request.json.get('new_password')
        if not new_pass: return jsonify({"status": "error", "message": "Password required"}), 400
        # Save to Firebase permanently
        db.collection('System_Settings').document('credentials').set({'admin_password': new_pass}, merge=True)
        return jsonify({"status": "success"}), 200
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/admin/change-staff-password', methods=['POST'])
def change_staff_password():
    try:
        new_pass = request.json.get('new_password')
        if not new_pass: return jsonify({"status": "error", "message": "Password required"}), 400
        # Save to Firebase permanently
        db.collection('System_Settings').document('credentials').set({'staff_password': new_pass}, merge=True)
        return jsonify({"status": "success"}), 200
    except Exception as e: return jsonify({"status": "error"}), 500

# ==========================================
# 🚪 NEW FIREBASE ROOM MANAGEMENT APIs
# ==========================================

@app.route('/get-rooms', methods=['GET'])
def get_rooms():
    try:
        docs = db.collection('Library_Rooms').stream()
        rooms = [doc.to_dict().get('room_name') for doc in docs]

        # Auto-create the database if it is empty!
        if len(rooms) == 0:
            default_rooms = [
                "Room 501", "Room 502", "Room 503", "Room 504", "Room 505", "Room 506", "Room 507",
                "Room 601", "Room 602", "Room 701", "Room 702", "Room 801", "Room 802"
            ]
            batch = db.batch()
            for r in default_rooms:
                doc_ref = db.collection('Library_Rooms').document()
                batch.set(doc_ref, {'room_name': r})
            batch.commit()
            rooms = default_rooms

        rooms.sort()
        return jsonify({'status': 'success', 'rooms': rooms}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/add-room', methods=['POST'])
def add_room():
    try:
        room_name = request.json.get('room_name')
        if not room_name or not room_name.startswith("Room "):
            return jsonify({'status': 'error', 'message': "Must start with 'Room '"}), 400

        # Check for duplicates
        docs = db.collection('Library_Rooms').where('room_name', '==', room_name).stream()
        if any(docs):
            return jsonify({'status': 'error', 'message': 'Room already exists'}), 400

        db.collection('Library_Rooms').add({'room_name': room_name})
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'status': 'error'}), 500

@app.route('/admin/delete-room', methods=['POST'])
def delete_room():
    try:
        room_name = request.json.get('room_name')
        if not room_name: return jsonify({'status': 'error'}), 400

        docs = db.collection('Library_Rooms').where('room_name', '==', room_name).stream()
        deleted = False
        
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            deleted = True
            
        if not deleted: return jsonify({'status': 'error', 'message': 'Room not found'}), 404
        
        batch.commit()
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'status': 'error'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)