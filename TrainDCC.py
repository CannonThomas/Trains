# TrainDCC.py

class TrainDCC:
    """
    Simple DCC helper / placeholder.
    Keep this only if another file imports TrainDCC directly.
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.current_speed = 0
        self.direction = "FORWARD"

    def log(self, msg: str):
        self.logger(msg)

    def set_speed(self, speed, forward=True):
        self.current_speed = speed
        self.direction = "FORWARD" if forward else "REVERSE"
        self.log(f"[DCC] Speed set to {speed}, direction={self.direction}")

    def stop(self):
        self.current_speed = 0
        self.log("[DCC] Train stopped")

    def horn(self):
        self.log("[DCC] Horn activated")

    def forward(self, speed):
        self.set_speed(speed, forward=True)

    def reverse(self, speed):
        self.set_speed(speed, forward=False)