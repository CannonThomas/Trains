# dcc_hbridge_test.py

import time
import train_config
from TrainIO import TrainIO
from train_config import LOCO_ADDRESS

train_config.MOCK_MODE = False

def log(msg: str):
    print(msg)

io = TrainIO(logger=log)

print("Starting H-bridge DCC test...")
print("Make sure:")
print(" - Pi ground and H-bridge logic ground are common")
print(" - external 15V powers the H-bridge, NOT the Pi")
print(" - H-bridge outputs go to rails")
print(" - test with NO locomotive first if possible")

time.sleep(2)

print("\nSending idle packet burst...")
io.dcc_idle()
time.sleep(1)

print("\nSending forward command...")
io.dcc_loco_speed(LOCO_ADDRESS, 8, True)
time.sleep(2)

print("\nSending stop command...")
io.dcc_loco_speed(LOCO_ADDRESS, 0, True)
time.sleep(1)

print("\nSending reverse command...")
io.dcc_loco_speed(LOCO_ADDRESS, 6, False)
time.sleep(2)

print("\nSending final stop...")
io.dcc_loco_speed(LOCO_ADDRESS, 0, True)

print("\nDone.")