# train_config.py
import json
import os

WINDOW_TITLE = "Train Sorter Control"
WINDOW_SIZE = "1200x950"

MOCK_MODE = False

_ROSTER_FILE = os.path.join(os.path.dirname(__file__), "car_roster.json")


def load_roster() -> dict:
    if os.path.exists(_ROSTER_FILE):
        try:
            with open(_ROSTER_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_roster(roster: dict):
    with open(_ROSTER_FILE, "w") as f:
        json.dump(roster, f, indent=2)


# Populated at startup from car_roster.json; updated live via GUI registration
CAR_ROSTER: dict = load_roster()

# Bachmann default short DCC address
LOCO_ADDRESS = 3

# ── Switches ────────────────────────────────────────────────────────────────
# Each switch has two solenoid coil pins (LEFT and RIGHT).
# A 1 ms HIGH pulse fires the coil; no steady-state current needed.
SWITCH_PINS = {
    "S1": {"LEFT": 12, "RIGHT": 13},   # Pin 32 / Pin 33
    "S2": {"LEFT": 16, "RIGHT": 19},   # Pin 36 / Pin 35
    "S3": {"LEFT": 20, "RIGHT": 21},   # Pin 38 / Pin 40
}

# Which direction diverts toward the SIDING track for each switch.
# Flip "LEFT" → "RIGHT" if a switch is physically wired the other way.
SWITCH_SIDING_DIR = {"S1": "LEFT", "S2": "LEFT", "S3": "LEFT"}

SWITCH_PULSE_SEC = 0.001   # 1 ms solenoid impulse

# ── RFID readers ─────────────────────────────────────────────────────────────
# 4 × RC522 on shared SPI bus:
#   MOSI → GPIO10 (Pin 19), MISO → GPIO9 (Pin 21), SCLK → GPIO11 (Pin 23)
# IMPORTANT: add "dtoverlay=spi0-0cs" to /boot/firmware/config.txt so the
# kernel SPI driver does not claim any CE pin and we can manage all CS pins
# ourselves with lgpio.
RFID_READERS = [
    {"name": "RFID1", "cs":  8, "rst": 22},  # SDA→GPIO8  (Pin 24), RST→GPIO22 (Pin 15)
    {"name": "RFID2", "cs":  7, "rst": 26},  # SDA→GPIO7  (Pin 26), RST→GPIO26 (Pin 37)
    {"name": "RFID3", "cs": 25, "rst": 27},  # SDA→GPIO25 (Pin 22), RST→GPIO27 (Pin 13)
    {"name": "RFID4", "cs": 24, "rst": 17},  # SDA→GPIO24 (Pin 18), RST→GPIO17 (Pin 11)
]

# ── DCC / H-bridge ───────────────────────────────────────────────────────────
DCC_PINS = {"ENA": 18, "IN1": 23, "IN2": 24}

# ── Sorting timings (seconds) ─────────────────────────────────────────────────
APPROACH_SEC        = 2.0
BACK_IN_SEC         = 2.0
DECOUPLE_SETTLE_SEC = 0.5
PULL_OUT_SEC        = 2.0
RETURN_TO_LOOP_SEC  = 3.0

# ── Motion speeds (0–126 DCC steps) ──────────────────────────────────────────
APPROACH_SPEED    = 20
BACK_IN_SPEED     = 15
PULL_OUT_SPEED    = 20
VICTORY_LAP_SPEED = 25

# ── DCC scheduler ─────────────────────────────────────────────────────────────
DCC_REFRESH_SEC   = 0.03
DCC_PACKET_REPEAT = 3
DCC_IDLE_REPEAT   = 2
DCC_SPEED_MODE    = 28
