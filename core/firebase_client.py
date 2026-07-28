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
        
def get_latest_reading(patient_id):
    """Read the most recent mirrored reading for a patient from Firestore.
    Used on cloud deployments (IS_CLOUD=true) in place of serial_reader,
    since there is no UART hardware there. Returns the same shape as
    serial_reader.get_latest(), or an all-None/disconnected snapshot if
    nothing is found."""
    _init()
    empty = {"accel_x": None, "temp": None, "bpm": None, "worn": None,
             "connected": False, "age_seconds": None}
    if _db is None:
        return empty
    try:
        doc = _db.collection("patients").document(str(patient_id)).get()
        if not doc.exists:
            return empty
        data = doc.to_dict()
        last = data.get("last_reading")
        if not last:
            return empty
        ts = last.get("timestamp")
        connected = False
        age_seconds = None
        if ts is not None:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            ts_dt = ts if hasattr(ts, "tzinfo") else None
            if ts_dt is not None:
                age_seconds = (now - ts_dt).total_seconds()
                connected = age_seconds <= 15
        return {
            "accel_x": last.get("accel_x"),
            "temp": last.get("temp"),
            "bpm": last.get("bpm"),
            "worn": last.get("worn"),
            "connected": connected,
            "age_seconds": age_seconds,
        }
    except Exception as e:
        print(f"[FIREBASE] get_latest_reading failed: {e}")
        return empty

def get_db():
    """Expose the initialized Firestore client for generic collection
    access (hospitals, bands, patients) used by storage.py on cloud
    deployments."""
    _init()
    return _db


def fs_load_collection(collection_name):
    """Return every document in a collection as a list of plain dicts."""
    db = get_db()
    if db is None:
        return []
    try:
        docs = db.collection(collection_name).stream()
        return [d.to_dict() for d in docs]
    except Exception as e:
        print(f"[FIREBASE] fs_load_collection({collection_name}) failed: {e}")
        return []


def fs_save_doc(collection_name, doc_id, data):
    db = get_db()
    if db is None:
        return
    try:
        db.collection(collection_name).document(str(doc_id)).set(data)
    except Exception as e:
        print(f"[FIREBASE] fs_save_doc({collection_name}/{doc_id}) failed: {e}")


def fs_delete_doc(collection_name, doc_id):
    db = get_db()
    if db is None:
        return
    try:
        db.collection(collection_name).document(str(doc_id)).delete()
    except Exception as e:
        print(f"[FIREBASE] fs_delete_doc({collection_name}/{doc_id}) failed: {e}")
