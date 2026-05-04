# train_config.py
import json
import os

WINDOW_TITLE = "Train Sorter Control"
WINDOW_SIZE  = "900x750"

MOCK_MODE = False

# Pi 5 with kernel 6.12+ exposes 40-pin header on gpiochip0
GPIO_CHIP = 0

_ROSTER_FILE = os.path.join(os.path.dirname(__file__), "car_roster.json")


def load_roster() -> dict:
    if os.path.exists(_ROSTER_FILE):
        try:
            with open(_ROSTER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_roster(roster: dict):
    with open(_ROSTER_FILE, "w") as f:
        json.dump(roster, f, indent=2)


# Populated from car_roster.json at startup; updated live via GUI registration
CAR_ROSTER: dict = load_roster()

# ── Switches ──────────────────────────────────────────────────────────────────
# Each switch has two solenoid coil pins (LEFT and RIGHT).
# A 1 ms HIGH pulse fires the coil; no steady-state current needed.
SWITCH_PINS = {
    "S1": {"LEFT": 12, "RIGHT": 13},   # Pin 32 / Pin 33
    "S2": {"LEFT": 16, "RIGHT": 19},   # Pin 36 / Pin 35
    "S3": {"LEFT": 20, "RIGHT": 21},   # Pin 38 / Pin 40
}

# Which direction diverts toward the SIDING for each switch.
# Flip "LEFT" → "RIGHT" if a switch is physically wired the other way.
SWITCH_SIDING_DIR   = {"S1": "LEFT", "S2": "LEFT", "S3": "LEFT"}
SWITCH_PULSE_SEC    = 0.250   # 250 ms solenoid impulse

# RFID1 = entry reader (scans consist order)
# RFID2/3/4 = end of Track 1/2/3 (confirm drop)
ENTRY_READER_IDX  = 0
TRACK_READER_IDX  = {1: 1, 2: 2, 3: 3}   # track number → RFID reader index

# ── SPI bit-bang pins (shared by all 4 readers) ───────────────────────────────
SPI_MOSI = 10   # Pin 19
SPI_MISO = 9    # Pin 21
SPI_SCLK = 11   # Pin 23

# ── RFID readers ──────────────────────────────────────────────────────────────
# 4 × RC522 on shared SPI bus:
#   MOSI → GPIO10 (Pin 19), MISO → GPIO9 (Pin 21), SCLK → GPIO11 (Pin 23)
#
# IMPORTANT: add  dtoverlay=spi0-0cs  to /boot/firmware/config.txt and reboot.
# This frees all CE pins so lgpio can drive them as regular GPIO outputs.
RFID_READERS = [
    {"name": "RFID1", "cs":  8, "rst": 22},  # SDA→GPIO8  (Pin 24), RST→GPIO22 (Pin 15)
    {"name": "RFID2", "cs":  7, "rst": 26},  # SDA→GPIO7  (Pin 26), RST→GPIO26 (Pin 37)
    {"name": "RFID3", "cs": 25, "rst": 27},  # SDA→GPIO25 (Pin 22), RST→GPIO27 (Pin 13)
    {"name": "RFID4", "cs": 24, "rst": 17},  # SDA→GPIO24 (Pin 18), RST→GPIO17 (Pin 11)
]

# ── Track power (L298 H-bridge, PWM speed control) ────────────────────────────
# 15V supply → L298 → ~12V at rails (L298 has ~2-3V internal dropout).
# To cap output near 12V, we limit max PWM duty cycle.
TRACK_ENA_PIN     = 18   # Pin 12 — PWM speed (hardware-PWM capable)
TRACK_IN1_PIN     = 23   # Pin 16 — direction A
TRACK_IN2_PIN     = 4    # Pin 7  — direction B
TRACK_PWM_FREQ    = 1000    # 1 kHz — safe range for lgpio software PWM
TRACK_MAX_DUTY    = 92      # % cap so 15V-in → ~12V out (L298 dropout ~2V)
TRACK_INPUT_VOLTS = 15.0
TRACK_TARGET_VOLTS = 12.0
