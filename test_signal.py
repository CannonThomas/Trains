# dcc_test.py
from TrainDCC import TrainDCC

dcc = TrainDCC(pin_a=23, pin_b=24, pin_en=18, loco_address=3)

try:
    dcc.setup()
    dcc.test_signal()
finally:
    dcc.cleanup()