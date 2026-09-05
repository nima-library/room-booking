import hashlib
import os

# --- CONFIGURATION ---
# (Note: ADMIN_PASSWORD is not here because it is securely fetched from Firebase!)
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
