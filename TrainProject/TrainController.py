import time
import threading
from TrainDCC import TrainDCC
from TrainIO import TrainIO
from TrainRFID import TrainRFID

class Controller:
    def __init__(self, status_callback):
        self.status_callback = status_callback
        self.dcc = TrainDCC()
        self.io = TrainIO()
        self.rfid = TrainRFID()
        self.running = False

    def start_sort(self):
        if self.running:
            return
        self.running = True
        self.status_callback("SORTING STARTED")
        threading.Thread(target=self.sorting_loop, daemon=True).start()

    def sorting_loop(self):
        self.dcc.set_speed(20)
        self.io.crossing_on()

        while self.running:
            tag = self.rfid.read_tag()
            if tag:
                self.status_callback(f"RFID detected: {tag}")
                track = self.decide_track(tag)
                self.io.set_turnout(track)
                time.sleep(2)

        self.shutdown()

    def decide_track(self, tag):
        # Placeholder routing logic
        return "A" if int(tag[-1]) % 2 == 0 else "B"

    def manual_drive(self, direction):
        speed = 15 if direction == 1 else -15
        self.dcc.set_speed(speed)
        self.status_callback("Manual drive")

    def emergency_stop(self):
        self.running = False
        self.shutdown()
        self.status_callback("EMERGENCY STOP")

    def shutdown(self):
        self.dcc.stop()
        self.io.crossing_off()