# core/loop.py
# Smartband V001 — background tie-together loop (fresh rebuild)
# HSHL Project — Masrur
#
# Every 3s: read the latest real sensor snapshot, push it to the OLED,
# and if a patient is currently assigned to the active band, log history
# and evaluate alert thresholds.
import time
import threading
import core.serial_reader as serial_reader
import core.drivers as drivers
import core.storage as storage
import core.firebase_client as firebase_client

_thread = None
_stop_flag = threading.Event()

# Battery reporting isn't wired to real hardware yet (no fuel-gauge on Rev1).
# Shown as a fixed placeholder rather than a fabricated dynamic value.
PLACEHOLDER_BATTERY = 100

def _tick():
    snap = serial_reader.get_latest()
    connected = snap["connected"]
    drivers.oled_show_sensors(
        snap["accel_x"], snap["temp"], PLACEHOLDER_BATTERY,
        bpm=snap.get("bpm"), worn=snap.get("worn"), connected=connected,
    )
    if not connected:
        return
    active_band = storage.get_active_band()
    if not active_band or not active_band.get("patient_id"):
        return
    patient_id = active_band["patient_id"]
    reading = {"accel_x": snap["accel_x"], "temp": snap["temp"], "bpm": snap.get("bpm"), "worn": snap.get("worn")}
    storage.append_history(patient_id, reading)
    firebase_client.push_reading(patient_id, reading)
    storage.check_and_log_alert(patient_id, reading)

def _run():
    drivers.gpio_init()
    while not _stop_flag.is_set():
        try:
            _tick()
        except Exception as e:
            print(f"[LOOP] tick error: {e}")
        time.sleep(3)

def start():
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_flag.clear()
    _thread = threading.Thread(target=_run, name="tie-loop", daemon=True)
    _thread.start()

def stop():
    _stop_flag.set()
