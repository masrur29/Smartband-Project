# config/settings.py
# Smartband V001 — Pi-side configuration (fresh rebuild)
# HSHL Project — Masrur

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── Serial link to Rev1 (CC2640R2F firmware over UART) ───────────
# Pi 5 note: /dev/serial0 maps to the internal debug UART (ttyAMA10),
# NOT the GPIO14/15 header UART. Always use /dev/ttyAMA0 explicitly.
UART_PORT = "/dev/ttyAMA0"
BAUD_RATE = 115200
SERIAL_READ_TIMEOUT = 2.0          # seconds, per line read
STALE_AFTER_SECONDS = 10           # if no line received in this long, mark band "offline"

# Actual line format confirmed by capturing raw UART output on the Pi
# (`cat /dev/ttyAMA0`) — all fields arrive together on ONE line every ~3s:
#   Acceleration=<int>mg Temperature=<float>C  HEART_RATE=<int> BPM WORN=<0|1>
#
# Note this is different from earlier assumptions in this project (no
# "ACCEL_X="/"TEMP="/"IR_RAW=" prefixes, no per-line-per-sensor format, and
# no separate IR_RAW field — the firmware sends real BPM and a worn/not-worn
# flag directly instead).

# ── Alert thresholds (based on real sensor fields only) ──────────
TEMP_HIGH_LIMIT = 38.5     # deg C — fever
ACCEL_HIGH_LIMIT = 2000    # mg — sudden shock / fall-like spike
BPM_LOW_LIMIT = 40         # bpm — bradycardia
BPM_HIGH_LIMIT = 140       # bpm — tachycardia

# ── OLED (SSD1306 via luma.oled, I2C on Rev1's shared bus) ────────
OLED_I2C_ADDRESS = 0x3C
OLED_I2C_PORT = 1

# ── Storage ────────────────────────────────────────────────────
HOSPITALS_FILE = os.path.join(DATA_DIR, "hospitals.json")
BANDS_FILE = os.path.join(DATA_DIR, "bands.json")
PATIENTS_FILE = os.path.join(DATA_DIR, "patients.json")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
ALERTS_FILE = os.path.join(DATA_DIR, "alerts.json")
os.makedirs(HISTORY_DIR, exist_ok=True)

HISTORY_MAX_POINTS = 500     # per-patient readings kept on disk
LIVE_HISTORY_POINTS = 60     # points kept in memory for live chart (~3 min at 3s/reading)

# ── Flask ──────────────────────────────────────────────────────
SECRET_KEY = "dev-key-change-me"   # only used for flash messages / session
DEBUG = True
HOST = "0.0.0.0"
PORT = 5000
