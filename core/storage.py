# core/storage.py
# Smartband V001 — persistence layer (fresh rebuild)
# HSHL Project — Masrur
#
# Local JSON files on the Pi (IS_CLOUD=false). On cloud deployments
# (IS_CLOUD=true, e.g. Render), hospitals/bands/patients are read and
# written to Firestore instead, since Render's filesystem is ephemeral
# and resets on every restart/redeploy. History and alerts remain local
# JSON in both cases for now (lower priority, larger data volume).

import os
import json
import random
import string
import threading
from datetime import datetime

from config.settings import (
    HOSPITALS_FILE, BANDS_FILE, PATIENTS_FILE, HISTORY_DIR, ALERTS_FILE,
    HISTORY_MAX_POINTS, TEMP_HIGH_LIMIT, ACCEL_HIGH_LIMIT,
    BPM_LOW_LIMIT, BPM_HIGH_LIMIT, SPO2_LOW_LIMIT, IS_CLOUD,
)
import core.firebase_client as firebase_client

_lock = threading.Lock()


# ── generic json helpers (Pi / local mode) ──────────────────────
def _load(path, default):
    if not os.path.exists(path):
        _save(path, default)
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ── Hospitals ──────────────────────────────────────────────────
def load_hospitals():
    if IS_CLOUD:
        return firebase_client.fs_load_collection("hospitals")
    return _load(HOSPITALS_FILE, [])


def save_hospitals(hospitals):
    if IS_CLOUD:
        for h in hospitals:
            firebase_client.fs_save_doc("hospitals", h["id"], h)
        return
    with _lock:
        _save(HOSPITALS_FILE, hospitals)


def get_hospital(hospital_id):
    return next((h for h in load_hospitals() if h["id"] == hospital_id), None)


def create_hospital(name, password):
    hid = "H" + "".join(random.choices(string.digits, k=4))
    existing_ids = {h["id"] for h in load_hospitals()}
    while hid in existing_ids:
        hid = "H" + "".join(random.choices(string.digits, k=4))
    hospital = {"id": hid, "name": name, "password": password, "band_ids": []}
    if IS_CLOUD:
        firebase_client.fs_save_doc("hospitals", hid, hospital)
    else:
        with _lock:
            hospitals = load_hospitals()
            hospitals.append(hospital)
            _save(HOSPITALS_FILE, hospitals)
    return hospital


def authenticate_hospital(hospital_id, password):
    h = get_hospital(hospital_id)
    if h and h["password"] == password:
        return h
    return None


# ── Bands (physical devices) ──────────────────────────────────
def load_bands():
    if IS_CLOUD:
        return firebase_client.fs_load_collection("bands")
    return _load(BANDS_FILE, [])


def save_bands(bands):
    if IS_CLOUD:
        for b in bands:
            firebase_client.fs_save_doc("bands", b["band_id"], b)
        return
    with _lock:
        _save(BANDS_FILE, bands)


def _generate_band_id(existing):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(chars, k=6))
        bid = f"SB-{code}"
        if not any(b["band_id"] == bid for b in existing):
            return bid


def add_bands(hospital_id, count=1):
    bands = load_bands()
    hospitals = load_hospitals()
    hospital = next((h for h in hospitals if h["id"] == hospital_id), None)
    if not hospital:
        return []
    created = []
    for _ in range(count):
        bid = _generate_band_id(bands + created)
        band = {
            "band_id": bid,
            "hospital_id": hospital_id,
            "status": "available",
            "patient_id": None,
            "active": False,
        }
        created.append(band)
        if IS_CLOUD:
            firebase_client.fs_save_doc("bands", bid, band)
        hospital.setdefault("band_ids", []).append(bid)

    if IS_CLOUD:
        firebase_client.fs_save_doc("hospitals", hospital_id, hospital)
    else:
        with _lock:
            bands_all = load_bands() + created
            _save(BANDS_FILE, bands_all)
            hospitals_all = load_hospitals()
            for h in hospitals_all:
                if h["id"] == hospital_id:
                    h["band_ids"] = hospital["band_ids"]
            _save(HOSPITALS_FILE, hospitals_all)
    return created


def get_band(band_id):
    return next((b for b in load_bands() if b["band_id"] == band_id), None)


def get_active_band():
    return next((b for b in load_bands() if b.get("active")), None)


def set_active_band(band_id):
    bands = load_bands()
    for b in bands:
        b["active"] = (b["band_id"] == band_id)
    if IS_CLOUD:
        for b in bands:
            firebase_client.fs_save_doc("bands", b["band_id"], b)
    else:
        with _lock:
            _save(BANDS_FILE, bands)
    return get_band(band_id)


def allocate_band(band_id, patient_id):
    bands = load_bands()
    target = None
    for b in bands:
        if b["band_id"] == band_id:
            b["status"] = "in_use"
            b["patient_id"] = patient_id
            target = b
    if IS_CLOUD:
        if target:
            firebase_client.fs_save_doc("bands", band_id, target)
    else:
        with _lock:
            _save(BANDS_FILE, bands)


def release_band(band_id):
    bands = load_bands()
    target = None
    for b in bands:
        if b["band_id"] == band_id:
            b["status"] = "available"
            b["patient_id"] = None
            b["active"] = False
            target = b
    if IS_CLOUD:
        if target:
            firebase_client.fs_save_doc("bands", band_id, target)
    else:
        with _lock:
            _save(BANDS_FILE, bands)


# ── Patients ───────────────────────────────────────────────────
def load_patients():
    if IS_CLOUD:
        return firebase_client.fs_load_collection("patient_records")
    return _load(PATIENTS_FILE, [])


def save_patients(patients):
    if IS_CLOUD:
        for p in patients:
            firebase_client.fs_save_doc("patient_records", p["id"], p)
        return
    with _lock:
        _save(PATIENTS_FILE, patients)


def get_patient(patient_id):
    return next((p for p in load_patients() if p["id"] == patient_id), None)


def get_patient_by_band(band_id):
    return next((p for p in load_patients() if p.get("band_id") == band_id), None)


def register_patient(name, age, gender, condition, hospital_id, band_id,
                      dob=None, weight=None, height=None, city=None):
    patients = load_patients()
    n = len(patients) + 1
    existing_ids = {p["id"] for p in patients}
    while f"p{n:03d}" in existing_ids:
        n += 1
    patient = {
        "id": f"p{n:03d}",
        "name": name,
        "age": age,
        "gender": gender,
        "condition": condition,
        "hospital_id": hospital_id,
        "band_id": band_id,
        "dob": dob,
        "weight": weight,
        "height": height,
        "city": city,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    if IS_CLOUD:
        firebase_client.fs_save_doc("patient_records", patient["id"], patient)
    else:
        with _lock:
            patients.append(patient)
            _save(PATIENTS_FILE, patients)
    allocate_band(band_id, patient["id"])
    set_active_band(band_id)
    return patient


SELF_SERVICE_HOSPITAL_ID = "SELF"


def get_or_create_self_service_hospital():
    h = get_hospital(SELF_SERVICE_HOSPITAL_ID)
    if h:
        return h
    h = {"id": SELF_SERVICE_HOSPITAL_ID, "name": "Self-Registered Patients",
         "password": None, "band_ids": []}
    if IS_CLOUD:
        firebase_client.fs_save_doc("hospitals", SELF_SERVICE_HOSPITAL_ID, h)
    else:
        with _lock:
            hospitals = load_hospitals()
            hospitals.append(h)
            _save(HOSPITALS_FILE, hospitals)
    return h


def remove_patient(patient_id):
    patients = load_patients()
    patient = next((p for p in patients if p["id"] == patient_id), None)
    if IS_CLOUD:
        if patient:
            firebase_client.fs_delete_doc("patient_records", patient_id)
    else:
        with _lock:
            patients = [p for p in patients if p["id"] != patient_id]
            _save(PATIENTS_FILE, patients)
    if patient:
        release_band(patient["band_id"])
    return patient

def claim_patient_for_hospital(band_id, hospital_id):
    """Reassign an existing patient (found via their Band ID) to a
    different hospital — used when a hospital wants to take over
    monitoring a self-registered patient instead of leaving them under
    the generic SELF hospital."""
    patient = get_patient_by_band(band_id)
    if not patient:
        return None
    patient["hospital_id"] = hospital_id
    if IS_CLOUD:
        firebase_client.fs_save_doc("patient_records", patient["id"], patient)
    else:
        with _lock:
            patients = load_patients()
            for p in patients:
                if p["id"] == patient["id"]:
                    p["hospital_id"] = hospital_id
            _save(PATIENTS_FILE, patients)
    return patient


def patients_for_hospital(hospital_id):
    return [p for p in load_patients() if p["hospital_id"] == hospital_id]


# ── History (per patient, real readings only — local JSON in both modes) ──
def _history_path(patient_id):
    return os.path.join(HISTORY_DIR, f"{patient_id}.json")


def append_history(patient_id, reading):
    if IS_CLOUD:
        return  # Firestore's readings subcollection (firebase_client.push_reading) covers this on cloud
    path = _history_path(patient_id)
    with _lock:
        history = _load(path, [])
        history.append({
            "t": datetime.now().isoformat(timespec="seconds"),
            "accel_x": reading.get("accel_x"),
            "temp": reading.get("temp"),
            "bpm": reading.get("bpm"),
            "worn": reading.get("worn"),
            "spo2": reading.get("spo2"),
        })
        if len(history) > HISTORY_MAX_POINTS:
            history = history[-HISTORY_MAX_POINTS:]
        _save(path, history)


def get_history(patient_id):
    if IS_CLOUD:
        db = firebase_client.get_db()
        if db is None:
            return []
        try:
            docs = (db.collection("patients").document(patient_id)
                      .collection("readings").order_by("timestamp").limit(HISTORY_MAX_POINTS).stream())
            out = []
            for d in docs:
                data = d.to_dict()
                ts = data.get("timestamp")
                out.append({
                    "t": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "accel_x": data.get("accel_x"),
                    "temp": data.get("temp"),
                    "bpm": data.get("bpm"),
                    "worn": data.get("worn"),
                    "spo2": data.get("spo2"),
                })
            return out
        except Exception as e:
            print(f"[FIREBASE] get_history failed: {e}")
            return []
    return _load(_history_path(patient_id), [])


# ── Alerts (derived from real thresholds only) ─────────────────
def load_alerts():
    if IS_CLOUD:
        return firebase_client.fs_load_collection("alerts")
    return _load(ALERTS_FILE, [])


def _save_alerts(alerts):
    if IS_CLOUD:
        return  # individual alerts saved directly in check_and_log_alert on cloud
    _save(ALERTS_FILE, alerts)


def check_and_log_alert(patient_id, reading):
    triggered = []
    if reading.get("temp") is not None and reading["temp"] > TEMP_HIGH_LIMIT:
        triggered.append("FEVER")
    if reading.get("accel_x") is not None and abs(reading["accel_x"]) > ACCEL_HIGH_LIMIT:
        triggered.append("SHOCK")
    if reading.get("worn") is False:
        triggered.append("BAND_NOT_WORN")
    if reading.get("bpm") is not None:
        if reading["bpm"] < BPM_LOW_LIMIT:
            triggered.append("BRADYCARDIA")
        elif reading["bpm"] > BPM_HIGH_LIMIT:
            triggered.append("TACHYCARDIA")
    if reading.get("spo2") is not None and reading["spo2"] < SPO2_LOW_LIMIT:
        triggered.append("LOW_SPO2")

    if triggered:
        alert = {
            "patient_id": patient_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "triggered_by": triggered,
            "reading": reading,
        }
        if IS_CLOUD:
            alert_id = f"{patient_id}_{datetime.now().timestamp()}"
            firebase_client.fs_save_doc("alerts", alert_id, alert)
        else:
            with _lock:
                alerts = load_alerts()
                alerts.append(alert)
                alerts = alerts[-500:]
                _save_alerts(alerts)
    return triggered


def alerts_for_patient(patient_id):
    return [a for a in load_alerts() if a["patient_id"] == patient_id]


def all_alerts():
    return load_alerts()
