# core/storage.py
# Smartband V001 — persistence layer (fresh rebuild)
# HSHL Project — Masrur
#
# Plain JSON files. One physical Rev1 band exists right now, but the data
# model supports multiple registered bands (for the hospital workflow) —
# only whichever band is marked "active" is bound to the live UART feed.

import os
import json
import random
import string
import threading
from datetime import datetime

from config.settings import (
    HOSPITALS_FILE, BANDS_FILE, PATIENTS_FILE, HISTORY_DIR, ALERTS_FILE,
    HISTORY_MAX_POINTS, TEMP_HIGH_LIMIT, ACCEL_HIGH_LIMIT,
    BPM_LOW_LIMIT, BPM_HIGH_LIMIT,
)

_lock = threading.Lock()


# ── generic json helpers ──────────────────────────────────────
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
    return _load(HOSPITALS_FILE, [])


def save_hospitals(hospitals):
    with _lock:
        _save(HOSPITALS_FILE, hospitals)


def get_hospital(hospital_id):
    return next((h for h in load_hospitals() if h["id"] == hospital_id), None)


def create_hospital(name, password):
    with _lock:
        hospitals = load_hospitals()
        hid = "H" + "".join(random.choices(string.digits, k=4))
        while any(h["id"] == hid for h in hospitals):
            hid = "H" + "".join(random.choices(string.digits, k=4))
        hospital = {"id": hid, "name": name, "password": password, "band_ids": []}
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
    return _load(BANDS_FILE, [])


def save_bands(bands):
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
    with _lock:
        bands = load_bands()
        hospitals = load_hospitals()
        hospital = next((h for h in hospitals if h["id"] == hospital_id), None)
        if not hospital:
            return []
        created = []
        for _ in range(count):
            bid = _generate_band_id(bands)
            band = {
                "band_id": bid,
                "hospital_id": hospital_id,
                "status": "available",   # available | in_use
                "patient_id": None,
                "active": False,          # bound to the live UART feed?
            }
            bands.append(band)
            hospital["band_ids"].append(bid)
            created.append(band)
        _save(BANDS_FILE, bands)
        _save(HOSPITALS_FILE, hospitals)
        return created


def get_band(band_id):
    return next((b for b in load_bands() if b["band_id"] == band_id), None)


def get_active_band():
    """The band currently bound to the real UART feed, if any."""
    return next((b for b in load_bands() if b.get("active")), None)


def set_active_band(band_id):
    """Bind the live UART feed to this band, unbinding any previous one.
    Only one band can be 'active' at a time — this reflects the physical
    reality that there is a single Rev1 unit wired to this Pi."""
    with _lock:
        bands = load_bands()
        for b in bands:
            b["active"] = (b["band_id"] == band_id)
        _save(BANDS_FILE, bands)
    return get_band(band_id)


def allocate_band(band_id, patient_id):
    with _lock:
        bands = load_bands()
        for b in bands:
            if b["band_id"] == band_id:
                b["status"] = "in_use"
                b["patient_id"] = patient_id
        _save(BANDS_FILE, bands)


def release_band(band_id):
    with _lock:
        bands = load_bands()
        for b in bands:
            if b["band_id"] == band_id:
                b["status"] = "available"
                b["patient_id"] = None
                b["active"] = False
        _save(BANDS_FILE, bands)


# ── Patients ───────────────────────────────────────────────────
def load_patients():
    return _load(PATIENTS_FILE, [])


def save_patients(patients):
    with _lock:
        _save(PATIENTS_FILE, patients)


def get_patient(patient_id):
    return next((p for p in load_patients() if p["id"] == patient_id), None)


def get_patient_by_band(band_id):
    return next((p for p in load_patients() if p.get("band_id") == band_id), None)


def register_patient(name, age, gender, condition, hospital_id, band_id,
                      dob=None, weight=None, height=None, city=None):
    with _lock:
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
        patients.append(patient)
        _save(PATIENTS_FILE, patients)
        allocate_band(band_id, patient["id"])
    set_active_band(band_id)
    return patient


SELF_SERVICE_HOSPITAL_ID = "SELF"


def get_or_create_self_service_hospital():
    """A fixed hospital record that self-registered patients (via /register)
    are attached to, so they still show up on a normal doctor dashboard
    without requiring the person wearing the band to go through hospital
    login first."""
    with _lock:
        hospitals = load_hospitals()
        h = next((x for x in hospitals if x["id"] == SELF_SERVICE_HOSPITAL_ID), None)
        if h:
            return h
        h = {"id": SELF_SERVICE_HOSPITAL_ID, "name": "Self-Registered Patients",
             "password": None, "band_ids": []}
        hospitals.append(h)
        _save(HOSPITALS_FILE, hospitals)
        return h


def remove_patient(patient_id):
    with _lock:
        patients = load_patients()
        patient = next((p for p in patients if p["id"] == patient_id), None)
        patients = [p for p in patients if p["id"] != patient_id]
        _save(PATIENTS_FILE, patients)
    if patient:
        release_band(patient["band_id"])
    return patient


def patients_for_hospital(hospital_id):
    return [p for p in load_patients() if p["hospital_id"] == hospital_id]


# ── History (per patient, real readings only) ─────────────────
def _history_path(patient_id):
    return os.path.join(HISTORY_DIR, f"{patient_id}.json")


def append_history(patient_id, reading):
    path = _history_path(patient_id)
    with _lock:
        history = _load(path, [])
        history.append({
            "t": datetime.now().isoformat(timespec="seconds"),
            "accel_x": reading.get("accel_x"),
            "temp": reading.get("temp"),
            "bpm": reading.get("bpm"),
            "worn": reading.get("worn"),
        })
        if len(history) > HISTORY_MAX_POINTS:
            history = history[-HISTORY_MAX_POINTS:]
        _save(path, history)


def get_history(patient_id):
    return _load(_history_path(patient_id), [])


# ── Alerts (derived from real thresholds only) ─────────────────
def load_alerts():
    return _load(ALERTS_FILE, [])


def _save_alerts(alerts):
    _save(ALERTS_FILE, alerts)


def check_and_log_alert(patient_id, reading):
    """Evaluate a reading against thresholds; append an alert entry if any
    fire. Returns the list of triggered alert codes (may be empty)."""
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

    if triggered:
        with _lock:
            alerts = load_alerts()
            alerts.append({
                "patient_id": patient_id,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "triggered_by": triggered,
                "reading": reading,
            })
            alerts = alerts[-500:]
            _save_alerts(alerts)
    return triggered


def alerts_for_patient(patient_id):
    return [a for a in load_alerts() if a["patient_id"] == patient_id]


def all_alerts():
    return load_alerts()
