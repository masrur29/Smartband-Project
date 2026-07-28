# Smartband V001 — Pi Companion (fresh rebuild v2)

## IMPORTANT — the directory-case bug that broke your last run

Linux treats `~/Smartband` and `~/smartband` as two different folders.
Your `venv` lives in one of them, and you `cd`'d into the other — that's
why `source venv/bin/activate` failed with "No such file or directory",
and it's the most likely reason old/incomplete code was running when you
saw only the hospital dashboard.

**Pick ONE folder and stick to it.** These instructions assume
`~/Smartband` (capital S), since that's the one you said you want to use.
Delete or rename the old lowercase `~/smartband` folder so there's no
ambiguity, or at least don't have both on your PATH/history at once.

## First-time setup (run once)

```bash
cd ~
rm -rf Smartband        # wipe any old/partial copy — skip if you want to keep other files in it
mkdir Smartband
cd Smartband
# copy/unzip this project's contents into ~/Smartband so app.py sits directly at ~/Smartband/app.py
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Every time you run it

```bash
cd ~/Smartband
source venv/bin/activate
python3 app.py
```

Then from another device on the same network, open:

```
http://<pi-ip>:5000/
```

This redirects to the hospital login/register page. From there:
1. Register a hospital (or log in) → lands on the hospital dashboard.
2. Click "+ Add band" → creates an `SB-XXXXXX` band ID.
3. Click "Bind live feed" on that band → binds it to the one physical
   Rev1 UART feed on this Pi.
4. Fill in "Register patient", pick that band → the patient row appears
   with a link.
5. Click the patient's name → **this is the live dashboard**: heart
   rate, acceleration, and temperature update every 3 seconds straight
   from `/dev/ttyAMA0`. If the band isn't bound/worn yet it shows "--"
   and "No sensor data" rather than fake numbers.
6. "Doctor view" (top-right of the hospital dashboard) shows all
   patients for that hospital in one table with the same live values.

## Heart rate (BPM) — one firmware change still needed

The Pi side is fully wired to receive and display BPM, but **the CC2640R2F
firmware doesn't send it yet.** It only currently prints:

```
LIS331DLTR ACCEL_X=<int>mg
MAX30205 TEMP=<float>C
MAX30102 IR_RAW=<int>
```

The firmware already computes BPM internally (used for the OLED) in
`get_i2c_value_max3010x_heartrate_bpm()`. Add one more UART print line
next to wherever the other three are printed, e.g.:

```c
System_printf("MAX30102 BPM=%d\n", bpm);
```

(match whatever print call the other three lines actually use). Once
that's flashed, BPM will start appearing automatically on the OLED, the
patient dashboard, and the doctor table — no Pi-side changes needed.

Until then, BPM cells show "--", exactly like a sensor field with no
data yet — nothing is faked or simulated.

## What's new in v3

Added two pages from your older, richer prototype — rebuilt to only ever
show real sensor data, nothing fabricated:

- **`/register`** — a patient can self-register (name, DOB, gender, weight,
  height, city, condition) without going through hospital login. They get
  a Band ID back immediately. They're attached to a fixed hospital record
  (`SELF` — "Self-Registered Patients") so a doctor can find them without
  extra setup. A staff member still needs to open the hospital admin page
  and click "Bind live feed" on their band before real data shows up —
  only one Rev1 unit exists, so this can't be automatic.

- **`/fhir/<hospital_id>`** — FHIR R4-shaped observations, linked from the
  hospital admin page ("FHIR Lab" button). Only **Heart rate** (LOINC
  8867-4) and **Body temperature** (LOINC 8310-5) are coded as FHIR
  Observations, because those are the only two things Rev1 measures that
  map to a real vital-sign LOINC code. Acceleration and raw PPG (IR)
  counts show as separate, clearly-labeled "raw telemetry" — not coded as
  vitals. **SpO2, blood pressure, respiratory rate, stress/EDA, and HRV
  are never shown** — the old prototype simulated those; this one doesn't,
  since Rev1 doesn't measure them. A patient whose band isn't the one
  currently active just shows "No live observations" rather than a fake
  number.

- **Not included:** `summary.html` (steps/goals/trend page). That's the
  "steps feature and all the other things" you asked to leave out of the
  fresh rebuild — say the word if you actually want it back and I'll wire
  it to real history data instead of simulated steps/goals.


- Real bug fix: none needed in the app logic itself — I ran the full
  hospital → doctor → patient flow end-to-end and it worked correctly.
  Your "only hospital dashboard" symptom traces to the `~/Smartband` vs
  `~/smartband` directory mismatch above, not a code bug.
- Added: `bpm` field throughout (serial reader, storage/history, alert
  thresholds `BPM_LOW_LIMIT`/`BPM_HIGH_LIMIT`, OLED screen, patient
  dashboard card + chart line, doctor table column).
- Removed: the stray `{config,core,server,storage,templates,data,static}`
  literal folder that was left over in the last zip (harmless, but confusing).
- `data/` is intentionally left out of this zip — it's created fresh
  on first run (`hospitals.json`, `bands.json`, `patients.json`,
  `history/`, `alerts.json`), so you start clean.
