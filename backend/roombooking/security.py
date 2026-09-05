from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import jsonify, request

from .config import (
    ADMIN_EMAIL,
    JWT_ALGORITHM,
    JWT_EXPIRES_HOURS,
    JWT_SECRET,
    STAFF_EMAILS_COLLECTION,
)
from .firebase_config import db


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
