import jwt
from firebase_admin import auth as firebase_auth
from flask import Blueprint, jsonify, request

from ..config import ADMIN_EMAIL, JWT_ALGORITHM, JWT_SECRET
from ..security import (
    get_bearer_token,
    get_system_password,
    issue_token,
    normalize_email,
    resolve_role,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/login", methods=["POST"])
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


@auth_bp.route("/admin-login", methods=["POST"])
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


@auth_bp.route("/staff-login", methods=["POST"])
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


@auth_bp.route("/auth/verify", methods=["GET"])
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
