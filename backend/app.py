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
ADMIN_PASSWORD = "admin123" 

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "pvtanany@gmail.com"  
SENDER_PASSWORD = "ahwodhkibllbpypr" 

# --- HELPER: EMAIL FUNCTIONS ---
def send_confirmation_email(to_email, booking_data, token):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Booking Confirmed: {booking_data['room_id']} - Nima Library"
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
        msg['Subject'] = "⚠️ Booking Cancelled by Library - Nima Knowledge Centre"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-top: 5px solid #c0392b;">
            <h2 style="color: #c0392b;">Booking Cancelled</h2>
            <p>Hello <strong>{name}</strong>,</p>
            <p>Your reservation has been cancelled by the Library Admin.</p>
            <div style="background: #f9f9f9; padding: 15px; margin: 15px 0;">
                <p><strong>Room:</strong> {room}</p><p><strong>Date:</strong> {date}</p><p><strong>Time:</strong> {time}</p>
            </div>
            <p>Please contact the librarian if you have questions.</p>
        </div>
        """
        msg.attach(MIMEText(html_body, 'html'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e: print(f"Email Error: {e}")

# --- API ROUTES ---

@app.route('/confirm-booking', methods=['POST'])
def confirm_booking():
    try:
        data = request.json
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

        if data.get('email'):
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

        if user_email:
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
            doc.reference.delete()
            found = True
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

# ✅ NEW ROUTE: BLOCKS A RANGE OF HOURS FOR ALL ROOMS AT ONCE
@app.route('/admin/block-slots', methods=['POST'])
def block_slots():
    try:
        data = request.json
        date = data['date']
        slots = data['slots'] # Array of selected hours
        rooms = data['rooms'] # Array of all 13 rooms
        
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
        docs = db.collection('daily_slots').where('details.leader_roll_no', '==', roll_no).stream()
        bookings = [{"room_id": d.to_dict().get('room_id'), "date": d.to_dict().get('date'), "time_slot": d.to_dict().get('time_slot')} for d in docs]
        return jsonify({"status": "success", "bookings": bookings}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin-login', methods=['POST'])
def admin_login():
    if request.json.get('password') == ADMIN_PASSWORD: return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 401

@app.route('/admin/all-bookings', methods=['GET'])
def all_bookings():
    docs = db.collection('daily_slots').stream()
    data = [{"room_id": d.to_dict().get('room_id'), "date": d.to_dict().get('date'), "time_slot": d.to_dict().get('time_slot'), "leader": d.to_dict().get('details', {}).get('leader_name', 'Unknown'), "roll_no": d.to_dict().get('details', {}).get('leader_roll_no', 'N/A')} for d in docs]
    return jsonify({"bookings": data}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)