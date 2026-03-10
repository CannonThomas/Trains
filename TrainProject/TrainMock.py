# TrainMock.py

import time


class TrainMock:
    """
    Mock hardware helper for testing train motion, switch routing,
    crossing signals, and uncoupling behavior.
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.current_speed = 0
        self.direction = "FORWARD"
        self.switch_positions = {
            "LOOP": "LEFT",
            "S1": "LEFT",
            "S2": "LEFT",
            "S3": "LEFT",
        }

    def log(self, msg: str):
        self.logger(msg)

    # -----------------------------------------
    # Locomotive motion
    # -----------------------------------------
    def set_speed(self, speed, forward=True):
        self.current_speed = speed
        self.direction = "FORWARD" if forward else "REVERSE"
        self.log(f"[MOCK DCC] Speed set to {speed}, direction={self.direction}")

    def stop(self):
        self.current_speed = 0
        self.log("[MOCK DCC] STOP")

    def horn(self):
        self.log("[MOCK DCC] Horn activated")

    # -----------------------------------------
    # Crossing
    # -----------------------------------------
    def crossing_on(self):
        self.log("[MOCK IO] Crossing ON")

    def crossing_off(self):
        self.log("[MOCK IO] Crossing OFF")

    # -----------------------------------------
    # Switches
    # -----------------------------------------
    def set_switch(self, switch_name, position):
        self.switch_positions[switch_name] = position
        self.log(f"[MOCK IO] {switch_name} set to {position}")

    def set_turnout(self, track):
        """
        Backward-compatible helper if old code still calls set_turnout(track).
        """
        self.log(f"[MOCK IO] Legacy turnout request for Track {track}")

    # -----------------------------------------
    # Coupler
    # -----------------------------------------
    def decouple(self):
        self.log("[MOCK IO] Decoupler pulse fired")
        time.sleep(0.5)

    def couple(self):
        self.log("[MOCK IO] Coupling sequence")
        time.sleep(0.5)

    # -----------------------------------------
    # RFID
    # -----------------------------------------
    def read_tag(self):
        time.sleep(0.5)
        fake_tag = "1111AAAA"
        self.log(f"[MOCK RFID] Read tag: {fake_tag}")
        return fake_tag