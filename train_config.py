# train_config.py

WINDOW_TITLE = "Automated Train Sorter"
WINDOW_SIZE = "1100x850"

MOCK_MODE = False

CAR_ROSTER = {
    "CAR_A": {"rfid": "73899B1E", "default_track": 1},
    "CAR_B": {"rfid": "12345678", "default_track": 2},
    "CAR_C": {"rfid": "87654321", "default_track": 3},
    "CAR_D": {"rfid": "ABCDEF12", "default_track": 4},
}

DEFAULT_CONSIST_ORDER = ["CAR_A", "CAR_B", "CAR_C", "CAR_D"]

# Bachmann default short DCC address
LOCO_ADDRESS = 3

# Turnout / accessory GPIOs
GPIO_PINS = {
    "LOOP": 5,
    "S1": 6,
    "S2": 16,
    "S3": 20,
    "DECOUPLE": 21,
}

# DCC / H-bridge GPIOs
DCC_PINS = {
    "ENA": 18,
    "IN1": 23,
    "IN2": 24,
}

# Sorting timings
APPROACH_SEC = 2.0
BACK_IN_SEC = 2.0
DECOUPLE_SETTLE_SEC = 0.5
PULL_OUT_SEC = 2.0
RETURN_TO_LOOP_SEC = 3.0

# Motion speeds used by controller
APPROACH_SPEED = 20
BACK_IN_SPEED = 15
PULL_OUT_SPEED = 20
VICTORY_LAP_SPEED = 25

# DCC scheduler settings
DCC_REFRESH_SEC = 0.03
DCC_PACKET_REPEAT = 3
DCC_IDLE_REPEAT = 2
DCC_SPEED_MODE = 28