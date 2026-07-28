# core/firebase_client.py
# Smartband V001 — Firestore mirror for live readings (fresh rebuild)
# HSHL Project — Masrur
#
# Mirrors each logged reading to Firestore alongside the existing local
# JSON history in storage.py. Does not replace local storage — this is
# an additional write path so the cloud dashboard / Bluefy bridge share
# the same database as the Pi's local dashboard.
#
# Credentials: on the Pi, reads from a local JSON file. On Render (or
# any environment without that file), reads from the FIREBASE_CREDENTIALS
# environment variable instead, containing the full JSON contents.

import os
import json
from datetime import datetime, timezone

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except Exception as e:
    print(f"[FIREBASE] firebase_admin not available: {e}")
    FIREBASE_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_FILENAME = "health-monitor-hshl-firebase-adminsdk-fbsvc-a4e8678455.json"
CRED_PATH = os.path.join(BASE_DIR, CRED_FILENAME)

_db = None

def _init():
    global _db
    if _db is not None or not FIREBASE_AVAILABLE:
        return
    try:
        cred = None
        env_json = os.environ.get("FIREBASE_CREDENTIALS")
        if env_json:
            cred_dict = json.loads(env_json)
            cred = credentials.Certificate(cred_dict)
            print("[FIREBASE] Using credentials from FIREBASE_CREDENTIALS env var")
        elif os.path.exists(CRED_PATH):
            cred = credentials.Certificate(CRED_PATH)
            print(f"[FIREBASE] Using credentials from local file: {CRED_PATH}")
        else:
            print("[FIREBASE] No credentials found (neither env var nor local file)")
            return

        firebase_admin.initialize_app(cred)
        _db = firestore.client()
        print("[FIREBASE] Initialized Firestore client")
    except Exception as e:
        print(f"[FIREBASE] Init failed: {e}")
        _db = None

def push_reading(patient_id, reading):
    _init()
    if _db is None:
        return
    try:
        doc = dict(reading)
        doc["timestamp"] = datetime.now(timezone.utc)
        _db.collection("patients").document(str(patient_id)) \
           .collection("readings").add(doc)
        _db.collection("patients").document(str(patient_id)) \
           .set({"last_reading": doc}, merge=True)
    except Exception as e:
        print(f"[FIREBASE] push_reading failed: {e}")
