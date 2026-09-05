from flask import Flask
from flask_cors import CORS

from .routes.admin import admin_bp
from .routes.auth import auth_bp
from .routes.bookings import bookings_bp


def create_app():
    app = Flask(__name__)
    CORS(
        app,
        resources={r"/*": {"origins": ["*"]}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "DELETE", "OPTIONS"],
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(admin_bp)

    return app
