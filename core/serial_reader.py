# core/serial_reader.py
# Smartband V001 — real UART reader for Rev1 (fresh rebuild)
# HSHL Project — Masrur
#
# Actual line format confirmed by capturing raw UART output directly
# (`cat /dev/ttyAMA0` on the Pi), which is DIFFERENT from what earlier
# versions of this file assumed:
#
#   Acceleration=944mg Temperature=29.78C  HEART_RATE=0 BPM WORN=0
#
# All four fields arrive on one line, not one field per line. The firmware
# already computes real BPM and a worn/not-worn flag itself — there is no
# separate IR_RAW field at all (that was an incorrect assumption in an
# earlier version of this file and is now removed).
#
# Maintains one shared, thread-safe "latest reading" dict plus a short
# in-memory rolling history for the live chart. No simulation fallback —
# if the board isn't connected, state simply reports offline.

import re
import time
import threading
from collections import deque
from datetime import datetime

from config.settings import (
    UART_PORT, BAUD_RATE, SERIAL_READ_TIMEOUT,
    STALE_AFTER_SECONDS, LIVE_HISTORY_POINTS,
)

try:
    import serial
    PYSERIAL_AVAILABLE = True
except Exception as e:
    print(f"[SERIAL] pyserial not available: {e}")
    PYSERIAL_AVAILABLE = False

_ACCEL_RE = re.compile(r"Acceleration=(-?\d+)mg")
_TEMP_RE = re.compile(r"Temperature=(-?\d+\.?\d*)C")
_BPM_RE = re.compile(r"HEART_RATE=(-?\d+)\s*BPM")
_WORN_RE = re.compile(r"WORN=(\d+)")

_lock = threading.Lock()
_latest = {
    "accel_x": None,
    "temp": None,
    "bpm": None,
    "worn": None,           # 1 = band is being worn / good PPG contact, 0 = not worn
    "last_update": None,   # datetime of last complete-ish update
    "connected": False,
}
_history = deque(maxlen=LIVE_HISTORY_POINTS)

_thread = None
_stop_flag = threading.Event()


def get_latest():
    """Return a snapshot of the latest reading, with 'connected' recomputed
    against the staleness window."""
    with _lock:
        snap = dict(_latest)
    if snap["last_update"] is not None:
        age = (datetime.now() - snap["last_update"]).total_seconds()
        snap["connected"] = age <= STALE_AFTER_SECONDS
        snap["age_seconds"] = round(age, 1)
    else:
        snap["connected"] = False
        snap["age_seconds"] = None
    return snap


def get_live_history():
    with _lock:
        return list(_history)


def _apply_line(line):
    """Parse one line (which may contain several fields at once, e.g.
    'Acceleration=944mg Temperature=29.78C  HEART_RATE=0 BPM WORN=0')
    and merge whatever fields are present into the latest-reading state."""
    updated = False

    m = _ACCEL_RE.search(line)
    if m:
        with _lock:
            _latest["accel_x"] = int(m.group(1))
        updated = True

    m = _TEMP_RE.search(line)
    if m:
        with _lock:
            _latest["temp"] = float(m.group(1))
        updated = True

    m = _BPM_RE.search(line)
    if m:
        with _lock:
            _latest["bpm"] = int(m.group(1))
        updated = True

    m = _WORN_RE.search(line)
    if m:
        with _lock:
            _latest["worn"] = bool(int(m.group(1)))
        updated = True

    if updated:
        with _lock:
            _latest["last_update"] = datetime.now()
            _latest["connected"] = True
            # Only push a history point once we have accel + temp at least
            # once — bpm/worn are included when present but their absence
            # doesn't block history, they just show "--" / unknown.
            if _latest["accel_x"] is not None and _latest["temp"] is not None:
                _history.append({
                    "t": datetime.now().strftime("%H:%M:%S"),
                    "accel_x": _latest["accel_x"],
                    "temp": _latest["temp"],
                    "bpm": _latest["bpm"],
                    "worn": _latest["worn"],
                })
    return updated


def _run_loop():
    print(f"[SERIAL] Starting reader on {UART_PORT} @ {BAUD_RATE} baud")
    while not _stop_flag.is_set():
        if not PYSERIAL_AVAILABLE:
            time.sleep(5)
            continue
        ser = None
        try:
            ser = serial.Serial(UART_PORT, BAUD_RATE, timeout=SERIAL_READ_TIMEOUT)
            print(f"[SERIAL] Opened {UART_PORT}")
            while not _stop_flag.is_set():
                raw = ser.readline()
                if not raw:
                    continue
                try:
                    line = raw.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if line:
                    _apply_line(line)
        except Exception as e:
            print(f"[SERIAL] Error on {UART_PORT}: {e} — retrying in 3s")
            time.sleep(3)
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass


def start():
    """Start the background reader thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_flag.clear()
    _thread = threading.Thread(target=_run_loop, name="serial-reader", daemon=True)
    _thread.start()


def stop():
    _stop_flag.set()
