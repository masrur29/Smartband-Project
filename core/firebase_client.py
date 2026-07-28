# core/firebase_client.py
# Smartband V001 — Firestore mirror for live readings (fresh rebuild)
# HSHL Project — Masrur
#
# Mirrors each logged reading to Firestore alongside the existing local
# JSON history in storage.py. Does not replace local storage — this is
# an additional write path so the cloud dashboard / Bluefy bridge share
# the same database as the Pi's local dashboard.

import os
from datetime import datetime, timezone

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except Exception as e:
    print(f"[FIREBASE] firebase_admin not available: {e}")
    FIREBASE_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_PATH = os.path.join(BASE_DIR, "health-monitor-hshl-firebase-adminsdk-fbsvc-efd6416ef8.json")

_db = None

def _init():
    global _db
    if _db is not None or not FIREBASE_AVAILABLE:
        return
    try:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        _db = firestore.client()
        print("[FIREBASE] Initialized Firestore client")
    except Exception as e:
        print(f"[FIREBASE] Init failed: {e}")
        _db = None

def push_reading(patient_id, reading):
    """Write one reading to Firestore under patients/{patient_id}/readings.
    Silently no-ops if Firebase isn't available/initialized, so the local
    dashboard keeps working even if this fails."""
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