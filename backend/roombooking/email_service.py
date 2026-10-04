import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import SENDER_EMAIL, SENDER_PASSWORD, SMTP_PORT, SMTP_SERVER


def send_confirmation_email(to_email, booking_data, token):
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = (
            f"Booking Confirmed: {booking_data['room_id']} - NIMA Knowledge Centre"
        )
        cancel_link = f"https://nima-roombooking-backend.vercel.app/cancel-via-email?token={token}"
        recipient_id = booking_data.get("leader_roll_no", "Student")
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd;">
            <h2 style="color: #27ae60;">Booking Confirmed!</h2>
            <p>Hello {recipient_id},</p>
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
        greeting = name if name else "Student"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-top: 5px solid #c0392b;">
            <h2 style="color: #c0392b;">Booking Cancelled Successfully</h2>
            <p>Dear {greeting},</p>
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
