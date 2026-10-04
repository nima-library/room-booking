import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
import ast


def _parse_credentials(raw_value):
    value = raw_value.strip()

    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except Exception:
            continue
        if isinstance(parsed, str):
            value = parsed.strip()
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("FIREBASE_CREDENTIALS must contain a JSON object")


# 1. Check if we are on Vercel (looking for the text variable)
if os.environ.get("FIREBASE_CREDENTIALS"):
    # Convert the text secret back into a dict.
    # Support valid JSON, quoted JSON, and the common "Python dict pasted into env var" format.
    key_dict = _parse_credentials(os.environ.get("FIREBASE_CREDENTIALS"))
    cred = credentials.Certificate(key_dict)

# 2. Check if we are on Render/Laptop (looking for the file)
else:
    _backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _possible_paths = [
        "serviceAccountKey.json",
        os.path.join(_backend_dir, "serviceAccountKey.json"),
        "/etc/secrets/serviceAccountKey.json",
    ]
    key_file = next((p for p in _possible_paths if os.path.exists(p)), None)
    if key_file:
        cred = credentials.Certificate(key_file)
    else:
        raise Exception("No Firebase Key found! Check Vercel Env Vars or Local File.")

# Initialize
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
