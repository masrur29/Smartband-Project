# server/routes_hospital.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash

import core.storage as storage

hospital_bp = Blueprint("hospital", __name__)


@hospital_bp.route("/hospital/register", methods=["GET", "POST"])
def hospital_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        if not name or not password:
            flash("Name and password are required.")
            return redirect(url_for("hospital.hospital_register"))
        hospital = storage.create_hospital(name, password)
        return redirect(url_for("hospital.hospital_dashboard", hospital_id=hospital["id"]))
    return render_template("hospital_register.html")


@hospital_bp.route("/hospital/login", methods=["GET", "POST"])
def hospital_login():
    if request.method == "POST":
        hospital_id = request.form.get("hospital_id", "").strip()
        password = request.form.get("password", "").strip()
        hospital = storage.authenticate_hospital(hospital_id, password)
        if not hospital:
            flash("Invalid hospital ID or password.")
            return redirect(url_for("hospital.hospital_login"))
        return redirect(url_for("hospital.hospital_dashboard", hospital_id=hospital["id"]))
    return render_template("hospital_register.html", login_mode=True)


@hospital_bp.route("/hospital/<hospital_id>/dashboard")
def hospital_dashboard(hospital_id):
    hospital = storage.get_hospital(hospital_id)
    if not hospital:
        return redirect(url_for("hospital.hospital_login"))
    bands = [b for b in storage.load_bands() if b["hospital_id"] == hospital_id]
    patients = storage.patients_for_hospital(hospital_id)
    return render_template("hospital_dashboard.html", hospital=hospital, bands=bands, patients=patients)


@hospital_bp.route("/api/hospital/<hospital_id>/bands/add", methods=["POST"])
def api_add_bands(hospital_id):
    count = int(request.json.get("count", 1)) if request.is_json else int(request.form.get("count", 1))
    created = storage.add_bands(hospital_id, count)
    return jsonify(created)


@hospital_bp.route("/api/hospital/<hospital_id>/bands/<band_id>/activate", methods=["POST"])
def api_activate_band(hospital_id, band_id):
    """Bind the single physical UART feed to this band. Only one band can
    be active system-wide, reflecting the one Rev1 unit wired to this Pi."""
    band = storage.set_active_band(band_id)
    return jsonify(band)


@hospital_bp.route("/api/hospital/<hospital_id>/patients/register", methods=["POST"])
def api_register_patient(hospital_id):
    data = request.json if request.is_json else request.form
    patient = storage.register_patient(
        name=data.get("name"),
        age=int(data.get("age", 0) or 0),
        gender=data.get("gender"),
        condition=data.get("condition", ""),
        hospital_id=hospital_id,
        band_id=data.get("band_id"),
    )
    return jsonify(patient)


@hospital_bp.route("/api/hospital/patients/<patient_id>/discharge", methods=["POST"])
def api_discharge_patient(patient_id):
    patient = storage.remove_patient(patient_id)
    return jsonify(patient or {})

@hospital_bp.route("/hospital/<hospital_id>/claim", methods=["GET"])
def claim_patient_page(hospital_id):
    hospital = storage.get_hospital(hospital_id)
    if not hospital:
        return redirect(url_for("hospital.hospital_login"))
    return render_template("claim_patient.html", hospital=hospital)


@hospital_bp.route("/api/hospital/<hospital_id>/claim", methods=["POST"])
def api_claim_patient(hospital_id):
    data = request.json if request.is_json else request.form
    band_id = (data.get("band_id") or "").strip().upper()
    if not band_id:
        return jsonify({"success": False, "error": "Enter a Band ID."}), 400
    patient = storage.claim_patient_for_hospital(band_id, hospital_id)
    if not patient:
        return jsonify({"success": False, "error": "No patient found for that Band ID."}), 404
    return jsonify({"success": True, "patient_id": patient["id"], "name": patient["name"]})
    
@hospital_bp.route("/hospital/<hospital_id>/activate")
def activate_band_page(hospital_id):
    hospital = storage.get_hospital(hospital_id)
    if not hospital:
        return redirect(url_for("hospital.hospital_login"))
    return render_template("activate_band.html", hospital=hospital)
