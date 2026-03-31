import train_config
from TrainRFID import TrainRFID

# Force real hardware mode for this test only
train_config.MOCK_MODE = False

def log(msg: str):
    print(msg)

reader = TrainRFID(logger=log)

print("RFID test started. Tap a tag/card to the reader. Ctrl+C to quit.")

try:
    while True:
        tag = reader.read_tag(timeout_sec=0.5)
        if tag:
            car = reader.identify_car(tag)
            if car:
                track = reader.get_default_track(tag)
                print(f"[MATCH] UID={tag} -> {car} -> default Track {track}")
            else:
                print(f"[UNKNOWN] UID={tag}")
except KeyboardInterrupt:
    print("\nRFID test stopped.")