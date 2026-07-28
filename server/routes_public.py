# server/routes_public.py
# Smartband V001 — public self-service registration + FHIR view
# HSHL Project — Masrur
#
# Two pieces carried over from the earlier feature-rich prototype, rebuilt
# to only ever show real sensor data:
#
#  /register            — a patient can register themselves without going
#                          through hospital login first; they get a Band ID
#                          back. They're attached to a fixed "Self-Registered
#                          Patients" hospital so a doctor can still find them
#                          on a normal doctor dashboard.
#
#  /fhir/<hospital_id>   — FHIR R4-shaped observations built from whatever
#                          the currently active band is actually reporting
#                          over UART right now. Only two vitals are coded as
#                          FHIR Observations: Heart rate (LOINC 8867-4) and
#                          Body temperature (LOINC 8310-5), because those are
#                          the only two things Rev1 measures that map to a
#                          real vital-sign LOINC code. Acceleration and raw
#                          PPG (IR) counts are shown as plain telemetry, not
#                          coded as vitals, and NOT fabricated (SpO2, blood
#                          pressure, respiratory rate, stress/EDA, HRV are
#                          not on Rev1's sensor list — this view never shows
#                          numbers for those; earlier prototypes simulated
#                          them, this one deliberately does not).

from flask import Blueprint, render_template, request, jsonify

import core.storage as storage
import core.serial_reader as serial_reader

public_bp = Blueprint("public", __name__)


@public_bp.route("/find")
def find_page():
    return render_template("find.html")


@public_bp.route("/api/find-patient")
def api_find_patient():
    band_id = (request.args.get("band_id") or "").strip().upper()
    if not band_id:
        return jsonify({"success": False, "error": "Enter a Band ID."}), 400
    band = storage.get_band(band_id)
    if not band or not band.get("patient_id"):
        return jsonify({"success": False, "error": "No patient found for that Band ID."}), 404
    return jsonify({"success": True, "patient_id": band["patient_id"]})


# ── Self-service registration ───────────────────────────────────
@public_bp.route("/register")
def register_page():
    return render_template("register.html")


@public_bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "Full name is required."}), 400

    hospital = storage.get_or_create_self_service_hospital()

    # Auto-create a fresh band for this patient (self-service: one band per signup)
    created = storage.add_bands(hospital["id"], count=1)
    band = created[0]

    dob = data.get("birthDate") or None
    age = _age_from_dob(dob)

    weight = data.get("weight") or None
    height = data.get("height") or None

    patient = storage.register_patient(
        name=name,
        age=age,
        gender=data.get("gender") or "other",
        condition=data.get("condition") or "",
        hospital_id=hospital["id"],
        band_id=band["band_id"],
        dob=dob,
        weight=float(weight) if weight else None,
        height=float(height) if height else None,
        city=data.get("city") or None,
    )
    return jsonify({"success": True, "band_id": band["band_id"], "patient_id": patient["id"]})


def _age_from_dob(dob_str):
    if not dob_str:
        return None
    try:
        from datetime import date
        y, m, d = (int(x) for x in dob_str.split("-"))
        born = date(y, m, d)
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None


# ── FHIR view (real observations only) ────────────────────────────
@public_bp.route("/fhir/<hospital_id>")
def fhir_view(hospital_id):
    hospital = storage.get_hospital(hospital_id)
    if not hospital:
        return "Hospital not found", 404
    return render_template("fhir_view.html", hospital=hospital)


@public_bp.route("/api/fhir/<hospital_id>/bundle")
def api_fhir_bundle(hospital_id):
    """Build a FHIR-shaped bundle per patient using ONLY real, currently-
    available readings. A patient whose band isn't the active/live one (or
    who has no reading yet) simply gets an empty observation list — nothing
    is invented to fill the gap."""
    patients = storage.patients_for_hospital(hospital_id)
    out = []
    for p in patients:
        band = storage.get_band(p["band_id"])
        entries = []
        if band and band.get("active"):
            snap = serial_reader.get_latest()
            if snap.get("connected"):
                if snap.get("bpm") is not None:
                    entries.append(_obs("8867-4", "Heart rate", snap["bpm"], "bpm", "/min"))
                if snap.get("temp") is not None:
                    entries.append(_obs("8310-5", "Body temperature", round(snap["temp"], 1), "Cel", "Cel"))
        telemetry = None
        if band and band.get("active"):
            snap = serial_reader.get_latest()
            if snap.get("connected"):
                telemetry = {
                    "accel_x_mg": snap.get("accel_x"),
                    "worn": snap.get("worn"),
                }
        out.append({
            "id": p["id"],
            "name": p["name"],
            "age": p.get("age"),
            "gender": p.get("gender"),
            "birthDate": p.get("dob"),
            "city": p.get("city"),
            "weight": p.get("weight"),
            "height": p.get("height"),
            "condition": p.get("condition"),
            "band_id": p["band_id"],
            "live": bool(band and band.get("active") and serial_reader.get_latest().get("connected")),
            "fhir": {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": entries,
            },
            "telemetry": telemetry,
        })
    return jsonify(out)


def _obs(loinc_code, display_name, value, unit, ucum):
    return {
        "resource": {
            "resourceType": "Observation",
            "status": "final",
            "category": [{"coding": [{"code": "vital-signs"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc_code, "display": display_name}],
                      "text": display_name},
            "valueQuantity": {"value": value, "unit": ucum, "system": "http://unitsofmeasure.org", "code": ucum},
            "effectiveDateTime": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
    }
