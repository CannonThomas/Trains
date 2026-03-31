# train_config.py

MOCK_MODE = True

# -----------------------------
# Layout
# -----------------------------
TRACKS = [1, 2, 3, 4]
SWITCH_NAMES = ["LOOP", "S1", "S2", "S3"]

LEFT = "LEFT"
RIGHT = "RIGHT"

# LOOP switch:
#   LEFT  -> main sorting line
#   RIGHT -> victory lap
LOOP_TO_MAIN = LEFT
LOOP_TO_VICTORY = RIGHT

# Cascaded routing tree:
# S1 decides Track 1 or continue
# S2 decides Track 2 or continue
# S3 decides Track 3 or continue
# If all stay straight, the train reaches Track 4
BRANCH = RIGHT
STRAIGHT = LEFT

# -----------------------------
# Fixed 4-car roster
# -----------------------------
CAR_ROSTER = {
    "CAR_A": {"rfid": "1111AAAA", "default_track": 1},
    "CAR_B": {"rfid": "2222BBBB", "default_track": 2},
    "CAR_C": {"rfid": "3333CCCC", "default_track": 3},
    "CAR_D": {"rfid": "4444DDDD", "default_track": 4},
}

DEFAULT_CONSIST_ORDER = ["CAR_A", "CAR_B", "CAR_C", "CAR_D"]

# -----------------------------
# Timing constants
# -----------------------------
COUPLER_PULSE_SEC = 0.8
SWITCH_THROW_SEC = 0.4

# Motion timing
APPROACH_SEC = 1.0
BACK_IN_SEC = 1.3
DECOUPLE_SETTLE_SEC = 0.5
PULL_OUT_SEC = 1.0
RETURN_TO_LOOP_SEC = 1.0

# -----------------------------
# DCC
# -----------------------------
DCC_PREAMBLE_BITS = 14
LOCO_ADDRESS = 3

# Automated motion speeds
APPROACH_SPEED = 8
BACK_IN_SPEED = 6
PULL_OUT_SPEED = 8
VICTORY_LAP_SPEED = 7

# -----------------------------
# Hardware pin assignments
# -----------------------------
# DCC signal output (pigpio, hardware-timed)
DCC_GPIO_PIN = 18

# Solenoid switch pins (BCM numbering, per PCB schematic).
# THROWN fires to diverge; CLOSED fires to close/straight.
# Adjust CLOSED pins if your PCB differs.
SWITCH_PINS = {
    "LOOP": {"THROWN": 17, "CLOSED": 24},
    "S1":   {"THROWN": 27, "CLOSED": 25},
    "S2":   {"THROWN": 22, "CLOSED": 12},
    "S3":   {"THROWN": 23, "CLOSED": 16},
}

# -----------------------------
# GUI
# -----------------------------
WINDOW_TITLE = "Automated Train Sorter"
WINDOW_SIZE = "1080x760"