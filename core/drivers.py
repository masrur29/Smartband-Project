# core/drivers.py
# Smartband V001 — OLED driver (fresh rebuild)
# HSHL Project — Masrur
#
# Single static screen: the 3 real sensor values + a battery bar.
# No page rotation, no steps/activity screen, no simulated vitals.

from PIL import Image, ImageDraw, ImageFont
from config.settings import OLED_I2C_ADDRESS, OLED_I2C_PORT

device = None
hardware_available = False

print("[HARDWARE] Binding OLED (luma.oled, SSD1306, 128x64)...")
try:
    from luma.core.interface.serial import i2c as luma_i2c
    from luma.oled.device import ssd1306

    _serial = luma_i2c(port=OLED_I2C_PORT, address=OLED_I2C_ADDRESS)
    device = ssd1306(_serial)
    hardware_available = True
    print("[HARDWARE] SSD1306 bound.")
except Exception as e:
    print(f"[WARN] OLED not found ({e}) — running headless, OLED calls are no-ops.")


def _load_font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


_FONT_SM = _load_font(10)
_FONT_MD = _load_font(14)
_FONT_HDR = _load_font(11)


def _draw_battery_icon(draw, batt, x=104, y=2):
    draw.rectangle((x, y, x + 17, y + 9), outline=1, fill=0)
    draw.rectangle((x + 17, y + 2, x + 19, y + 7), fill=1)
    fw = max(0, min(14, int((batt / 100.0) * 14)))
    if fw > 0:
        draw.rectangle((x + 1, y + 1, x + 1 + fw, y + 8), fill=1)


def oled_show_sensors(accel_x, temp, battery, bpm=None, worn=None, connected=True):
    """Single static screen showing the real sensor values plus a battery
    bar. Values may be None if no reading has arrived yet."""
    img = Image.new("1", (128, 64), color=0)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle((0, 0, 127, 13), fill=1)
    draw.text((3, 1), "SMARTBAND V001", font=_FONT_HDR, fill=0)
    _draw_battery_icon(draw, battery)

    if not connected:
        draw.text((10, 26), "NO SENSOR DATA", font=_FONT_MD, fill=1)
        draw.text((10, 44), "check UART link", font=_FONT_SM, fill=1)
        _push(img)
        return

    # BPM (top row — the value people care about most)
    draw.text((2, 16), "BPM", font=_FONT_SM, fill=1)
    draw.text((60, 14), f"{bpm if bpm is not None else '--'}", font=_FONT_MD, fill=1)

    # Accel
    draw.text((2, 30), "ACCEL X", font=_FONT_SM, fill=1)
    draw.text((60, 28), f"{accel_x if accel_x is not None else '--'} mg", font=_FONT_SM, fill=1)

    # Temp
    draw.text((2, 42), "TEMP", font=_FONT_SM, fill=1)
    tstr = f"{temp:.1f} C" if temp is not None else "-- C"
    draw.text((60, 40), tstr, font=_FONT_SM, fill=1)

    # Worn status
    draw.text((2, 54), "WORN", font=_FONT_SM, fill=1)
    wstr = "YES" if worn else ("NO" if worn is not None else "--")
    draw.text((60, 52), wstr, font=_FONT_SM, fill=1)

    _push(img)


def _push(img):
    if hardware_available and device:
        device.display(img)


# ── GPIO stubs (pinctrl-based, Pi 5) — kept minimal for alert indicators ──
import subprocess

LED_RED = "27"
LED_GREEN = "26"
BUZZER = "17"


def _pin(pin, level):
    try:
        subprocess.run(["pinctrl", "set", pin, "op", "dh" if level else "dl"], capture_output=True)
    except Exception:
        pass


def gpio_init():
    for p in (LED_RED, LED_GREEN, BUZZER):
        try:
            subprocess.run(["pinctrl", "set", p, "op"], capture_output=True)
            _pin(p, False)
        except Exception:
            pass


def led_green_on():
    _pin(LED_RED, False)
    _pin(LED_GREEN, True)


def led_red_on():
    _pin(LED_GREEN, False)
    _pin(LED_RED, True)


def led_off():
    _pin(LED_RED, False)
    _pin(LED_GREEN, False)
