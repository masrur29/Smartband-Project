# app.py
# Smartband V001 — Pi-side Flask app (fresh rebuild)
# HSHL Project — Masrur
#
# Real UART sensor data only (no simulator). Three dashboards:
# patient (single band live view), doctor (per-hospital patient list),
# hospital (register hospital, add bands, register/discharge patients).

from flask import Flask, redirect, url_for

from config.settings import SECRET_KEY, DEBUG, HOST, PORT
import core.serial_reader as serial_reader
import core.loop as loop

from server.routes_patient import patient_bp
from server.routes_doctor import doctor_bp
from server.routes_hospital import hospital_bp
from server.routes_public import public_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(hospital_bp)
    app.register_blueprint(public_bp)

    @app.route("/")
    def root():
        return redirect(url_for("hospital.hospital_login"))

    return app


app = create_app()

if __name__ == "__main__":
    serial_reader.start()
    loop.start()
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
