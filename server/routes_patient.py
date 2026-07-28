# server/routes_patient.py
from flask import Blueprint, render_template, jsonify, abort

import core.storage as storage
import core.serial_reader as serial_reader

patient_bp = Blueprint("patient", __name__)


def _band_for_patient(patient):
    return storage.get_band(patient["band_id"])


@patient_bp.route("/patient/<patient_id>")
def patient_dashboard(patient_id):
    patient = storage.get_patient(patient_id)
    if not patient:
        abort(404)
    band = _band_for_patient(patient)
    return render_template("index.html", patient=patient, band=band)


@patient_bp.route("/api/patient/<patient_id>/live")
def patient_live(patient_id):
    patient = storage.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "not found"}), 404
    band = _band_for_patient(patient)
    if band and band.get("active"):
        snap = serial_reader.get_latest()
    else:
        snap = {"accel_x": None, "temp": None, "bpm": None, "worn": None, "connected": False, "age_seconds": None}
    return jsonify(snap)


@patient_bp.route("/api/patient/<patient_id>/history")
def patient_history(patient_id):
    if not storage.get_patient(patient_id):
        return jsonify({"error": "not found"}), 404
    return jsonify(storage.get_history(patient_id))


@patient_bp.route("/api/patient/<patient_id>/alerts")
def patient_alerts(patient_id):
    if not storage.get_patient(patient_id):
        return jsonify({"error": "not found"}), 404
    return jsonify(storage.alerts_for_patient(patient_id))
