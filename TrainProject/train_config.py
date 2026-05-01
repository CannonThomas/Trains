# train_config.py

MOCK_MODE = False

# -----------------------------
# Layout
# -----------------------------
TRACKS = [1, 2, 3, 4]

# No LOOP switch anymore
SWITCH_NAMES = ["S1", "S2", "S3"]

LEFT = "LEFT"
RIGHT = "RIGHT"

BRANCH = RIGHT
STRAIGHT = LEFT

# -----------------------------
# Switch GPIO
# 3 switches x 2 GPIOs each = 6 GPIOs
# -----------------------------
SWITCH_GPIO = {
    "S1_LEFT": 12,
    "S1_RIGHT": 13,

    "S2_LEFT": 16,
    "S2_RIGHT": 19,

    "S3_LEFT": 20,
    "S3_RIGHT": 21,
}

# -----------------------------
# RFID GPIO
# 4 readers = 3 shared SPI + 4 CS + 4 RST = 11 GPIOs
# -----------------------------
RFID_SPI_GPIO = {
    "MOSI": 10,
    "MISO": 9,
    "SCLK": 11,
}

RFID_CS_GPIO = {
    "RFID0_ENTRY": 8,
    "RFID1_S1": 7,
    "RFID2_S2": 25,
    "RFID3_S3": 24,
}

RFID_RST_GPIO = {
    "RFID0_ENTRY": 22,
    "RFID1_S1": 26,
    "RFID2_S2": 27,
    "RFID3_S3": 17,
}

RFID_READERS = {
    "RFID0_ENTRY": {
        "cs": RFID_CS_GPIO["RFID0_ENTRY"],
        "rst": RFID_RST_GPIO["RFID0_ENTRY"],
    },
    "RFID1_S1": {
        "cs": RFID_CS_GPIO["RFID1_S1"],
        "rst": RFID_RST_GPIO["RFID1_S1"],
    },
    "RFID2_S2": {
        "cs": RFID_CS_GPIO["RFID2_S2"],
        "rst": RFID_RST_GPIO["RFID2_S2"],
    },
    "RFID3_S3": {
        "cs": RFID_CS_GPIO["RFID3_S3"],
        "rst": RFID_RST_GPIO["RFID3_S3"],
    },
}

# -----------------------------
# Other GPIO
# -----------------------------
COUPLER_GPIO = 23
CROSSING_GPIO = 18

# -----------------------------
# Cars
# -----------------------------
CAR_ROSTER = {
    "CAR_A": {"rfid": "1111AAAA", "default_track": 1},
    "CAR_B": {"rfid": "2222BBBB", "default_track": 2},
    "CAR_C": {"rfid": "3333CCCC", "default_track": 3},
    "CAR_D": {"rfid": "4444DDDD", "default_track": 4},
}

DEFAULT_CONSIST_ORDER = ["CAR_A", "CAR_B", "CAR_C", "CAR_D"]

# -----------------------------
# Timing
# -----------------------------
SWITCH_THROW_SEC = 0.07
COUPLER_PULSE_SEC = 0.7

APPROACH_SEC = 1.0
BACK_IN_SEC = 1.2
DECOUPLE_SETTLE_SEC = 0.4
PULL_OUT_SEC = 1.0

# -----------------------------
# DCC placeholder
# -----------------------------
LOCO_ADDRESS = 3

APPROACH_SPEED = 8
BACK_IN_SPEED = 6
PULL_OUT_SPEED = 8

# -----------------------------
# GUI
# -----------------------------
WINDOW_TITLE = "Automated Train Sorter"
WINDOW_SIZE = "1100x750"