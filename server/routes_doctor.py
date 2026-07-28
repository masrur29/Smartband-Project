# server/routes_doctor.py
from flask import Blueprint, render_template, jsonify, abort

import core.storage as storage
import core.serial_reader as serial_reader
import core.firebase_client as firebase_client
from config.settings import IS_CLOUD

doctor_bp = Blueprint("doctor", __name__)


@doctor_bp.route("/doctor/<hospital_id>")
def doctor_dashboard(hospital_id):
    hospital = storage.get_hospital(hospital_id)
    if not hospital:
        abort(404)
    patients = storage.patients_for_hospital(hospital_id)
    return render_template("doctor.html", hospital=hospital, patients=patients)


@doctor_bp.route("/api/doctor/<hospital_id>/patients")
def doctor_patients(hospital_id):
    patients = storage.patients_for_hospital(hospital_id)
    out = []
    for p in patients:
        band = storage.get_band(p["band_id"])
        if IS_CLOUD:
            snap = firebase_client.get_latest_reading(p["id"])
        elif band and band.get("active"):
            snap = serial_reader.get_latest()
        else:
            snap = {"accel_x": None, "temp": None, "bpm": None, "worn": None, "connected": False}
        out.append({"patient": p, "band": band, "live": snap})
    return jsonify(out)


@doctor_bp.route("/api/doctor/<hospital_id>/alerts")
def doctor_alerts(hospital_id):
    patient_ids = {p["id"] for p in storage.patients_for_hospital(hospital_id)}
    alerts = [a for a in storage.all_alerts() if a["patient_id"] in patient_ids]
    return jsonify(alerts)
