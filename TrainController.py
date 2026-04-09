import threading
import time
from train_config import *
from TrainIO import TrainIO
from TrainRFID import TrainRFID


class TrainController:

    def __init__(self, logger=print):
        self.logger = logger
        self.io = TrainIO(logger=self.log)
        self.rfid = TrainRFID(logger=self.log)

        self.running = False
        self.sort_thread = None

        self.car_destinations = {
            car: info["default_track"] for car, info in CAR_ROSTER.items()
        }

        self.initial_consist = list(DEFAULT_CONSIST_ORDER)
        self.consist = list(DEFAULT_CONSIST_ORDER)

    def log(self, msg):
        self.logger(msg)

    # -----------------------------
    # SAFE THREAD START
    # -----------------------------
    def start_sorting_async(self):
        if self.sort_thread and self.sort_thread.is_alive():
            self.log("[SYSTEM] Already running")
            return

        self.sort_thread = threading.Thread(
            target=self.start_sorting,
            daemon=True
        )
        self.sort_thread.start()

    # -----------------------------
    def start_sorting(self):
        self.running = True
        self.log("[SYSTEM] Start sorting")

        while self.running and len(self.consist) > 0:
            time.sleep(1)

        self.running = False
        self.log("[SYSTEM] Done")

    def stop_sorting(self):
        self.running = False
        self.log("[SYSTEM] Stop")

    def shutdown(self):
        self.stop_sorting()
        if hasattr(self.io, "cleanup"):
            self.io.cleanup()