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

# 📧 EMAIL SETTINGS (UPDATED)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "pvtanany@gmail.com"
SENDER_PASSWORD = "ahwodhkibllbpypr" 

# --- HELPER: SEND EMAIL ---
def send_confirmation_email(to_email, booking_data, token):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Booking Confirmed: {booking_data['room_id']} - Nima Library"

        # The link points to your backend to handle cancellation
        cancel_link = f"https://nima-backend.vercel.app/cancel-via-email?token={token}"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #1e2a4a; padding: 20px; text-align: center; color: white;">
                <h2 style="margin: 0;">Booking Confirmed!</h2>
            </div>
            <div style="padding: 20px;">
                <p>Hello <strong>{booking_data['leader_name']}</strong>,</p>
                <p>Your discussion room has been successfully reserved.</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>📅 Date:</strong> {booking_data['date']}</p>
                    <p style="margin: 5px 0;"><strong>⏰ Time:</strong> {booking_data['time_slot']}</p>
                    <p style="margin: 5px 0;"><strong>🚪 Room:</strong> <span style="color: #3d5afe; font-weight: bold;">{booking_data['room_id']}</span></p>
                    <p style="margin: 5px 0;"><strong>🆔 Roll No:</strong> {booking_data['leader_roll_no']}</p>
                </div>

                <p style="color: #666; font-size: 14px;">If you can no longer make it, please cancel so others can use the room.</p>
                
                <div style="text-align: center; margin-top: 20px;">
                    <a href="{cancel_link}" style="background-color: #e74c3c; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">Cancel Booking</a>
                </div>
            </div>
            <div style="background-color: #eee; padding: 10px; text-align: center; font-size: 12px; color: #666;">
                Nima Library Discussion Deck
            </div>
        </div>
        """
        
        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

@firestore.transactional
def run_transaction(transaction, slot_ref, booking_data, token):
    snapshot = slot_ref.get(transaction=transaction)
    if snapshot.exists and snapshot.get('status') == 'booked':
        raise Exception("Slot already booked")

    transaction.set(slot_ref, {
        'status': 'booked',
        'date': booking_data.get('date'),          
        'time_slot': booking_data.get('time_slot'),
        'room_id': booking_data.get('room_id'),
        'cancel_token': token,  # Save the secret token
        'details': booking_data,
        'timestamp': firestore.SERVER_TIMESTAMP
    }, merge=True)

@app.route('/confirm-booking', methods=['POST'])
def confirm_booking():
    try:
        data = request.json
        slot_id = f"{data['room_id']}_{data['date']}_{data['time_slot']}"
        slot_ref = db.collection('daily_slots').document(slot_id)

        # Generate a unique token for cancellation
        cancel_token = str(uuid.uuid4())

        transaction = db.transaction()
        run_transaction(transaction, slot_ref, data, cancel_token)

        # Send Email in background
        if data.get('email'):
            send_confirmation_email(data['email'], data, cancel_token)

        return jsonify({"status": "success", "message": "Booking Confirmed!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# --- CANCEL VIA EMAIL LINK ---
@app.route('/cancel-via-email', methods=['GET'])
def cancel_via_email():
    try:
        token = request.args.get('token')
        if not token:
            return "Invalid Link", 400

        # Find the booking with this token
        docs = db.collection('daily_slots').where('cancel_token', '==', token).stream()
        
        found = False
        for doc in docs:
            doc.reference.delete()
            found = True
        
        if found:
            return """
            <html>
                <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                    <h1 style="color: #27ae60;">Booking Cancelled Successfully</h1>
                    <p>Your reservation has been removed.</p>
                </body>
            </html>
            """, 200
        else:
            return "<h1>Booking not found or already cancelled.</h1>", 404

    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/cancel-booking', methods=['POST'])
def cancel_booking():
    try:
        data = request.json
        slot_id = f"{data['room_id']}_{data['date']}_{data['time_slot']}"
        db.collection('daily_slots').document(slot_id).delete()
        return jsonify({"status": "success", "message": "Cancelled"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/get-bookings', methods=['GET'])
def get_bookings():
    try:
        date = request.args.get('date')
        docs = db.collection('daily_slots').where('date', '==', date).stream()
        bookings = []
        for doc in docs:
            data = doc.to_dict()
            bookings.append({
                "time_slot": data.get('time_slot'),
                "room_id": data.get('room_id')
            })
        return jsonify({"bookings": bookings}), 200
    except Exception as e: return jsonify({"status": "error"}), 400

@app.route('/my-bookings', methods=['GET'])
def my_bookings():
    try:
        roll_no = request.args.get('roll_no')
        docs = db.collection('daily_slots').where('details.leader_roll_no', '==', roll_no).stream()
        bookings = []
        for doc in docs:
            data = doc.to_dict()
            bookings.append({
                "room_id": data.get('room_id'),
                "date": data.get('date'),
                "time_slot": data.get('time_slot'),
                "purpose": data.get('details', {}).get('purpose')
            })
        return jsonify({"status": "success", "bookings": bookings}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin-login', methods=['POST'])
def admin_login():
    if request.json.get('password') == ADMIN_PASSWORD:
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 401

@app.route('/admin/all-bookings', methods=['GET'])
def all_bookings():
    docs = db.collection('daily_slots').stream()
    data = []
    for doc in docs:
        d = doc.to_dict()
        data.append({
            "room_id": d.get('room_id'), 
            "date": d.get('date'), 
            "time_slot": d.get('time_slot'), 
            "leader": d.get('details', {}).get('leader_name', 'Unknown'), 
            "roll_no": d.get('details', {}).get('leader_roll_no', 'N/A')
        })
    return jsonify({"bookings": data}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)