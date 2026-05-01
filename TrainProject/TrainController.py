# TrainController.py

from enum import Enum, auto
import time

from train_config import (
    CAR_ROSTER,
    DEFAULT_CONSIST_ORDER,
    LOCO_ADDRESS,
    APPROACH_SPEED,
    BACK_IN_SPEED,
    PULL_OUT_SPEED,
    APPROACH_SEC,
    BACK_IN_SEC,
    DECOUPLE_SETTLE_SEC,
    PULL_OUT_SEC,
)

from TrainIO import TrainIO
from TrainRFID import TrainRFID


class SortState(Enum):
    IDLE = auto()
    WAIT_FOR_RFID = auto()
    IDENTIFY_CAR = auto()
    ROUTE_SWITCHES = auto()
    MOVE_TO_TRACK = auto()
    DECOUPLE = auto()
    PULL_OUT = auto()
    NEXT_CAR = auto()
    COMPLETE = auto()
    ABORTED = auto()


class TrainController:
    def __init__(self, logger=print):
        self.logger = logger
        self.io = TrainIO(logger=self.log)
        self.rfid = TrainRFID(logger=self.log)

        self.state = SortState.IDLE
        self.running = False

        self.car_destinations = {
            car_name: info["default_track"]
            for car_name, info in CAR_ROSTER.items()
        }

        self.initial_consist = list(DEFAULT_CONSIST_ORDER)
        self.consist = list(DEFAULT_CONSIST_ORDER)

        self.track_contents = {
            1: [],
            2: [],
            3: [],
            4: [],
        }

        self.current_car = None
        self.current_reader = None
        self.current_tag = None
        self.current_target_track = None

        self.current_speed = 0
        self.current_direction_forward = True

    def log(self, msg):
        self.logger(msg)

    # -------------------------------------------------
    # Config
    # -------------------------------------------------
    def set_destination(self, car_name, track):
        if car_name not in self.car_destinations:
            self.log(f"[WARN] Unknown car: {car_name}")
            return

        if track not in [1, 2, 3, 4]:
            self.log(f"[WARN] Invalid destination: Track {track}")
            return

        self.car_destinations[car_name] = track
        self.log(f"[CFG] {car_name} -> Track {track}")

    def set_consist_order(self, cars):
        if sorted(cars) != sorted(DEFAULT_CONSIST_ORDER):
            self.log("[WARN] Invalid consist order ignored")
            return

        self.initial_consist = list(cars)
        self.consist = list(cars)
        self.log(f"[CFG] Consist order set to {self.consist}")

    # -------------------------------------------------
    # Loco helpers
    # -------------------------------------------------
    def loco_stop(self):
        self.current_speed = 0
        self.io.dcc_loco_speed(
            LOCO_ADDRESS,
            0,
            self.current_direction_forward,
        )
        self.log("[LOCO] Stop")

    def loco_forward(self, speed):
        self.current_speed = speed
        self.current_direction_forward = True
        self.io.dcc_loco_speed(LOCO_ADDRESS, speed, True)
        self.log(f"[LOCO] Forward speed {speed}")

    def loco_reverse(self, speed):
        self.current_speed = speed
        self.current_direction_forward = False
        self.io.dcc_loco_speed(LOCO_ADDRESS, speed, False)
        self.log(f"[LOCO] Reverse speed {speed}")

    # -------------------------------------------------
    # State machine
    # -------------------------------------------------
    def start_sorting(self):
        if self.running:
            self.log("[SYSTEM] Already running")
            return

        self.running = True
        self.state = SortState.WAIT_FOR_RFID

        self.log("[SYSTEM] Sorting state machine started")
        self.show_state()

    def step_state_machine(self):
        if not self.running:
            return

        if self.state == SortState.WAIT_FOR_RFID:
            self.state_wait_for_rfid()

        elif self.state == SortState.IDENTIFY_CAR:
            self.state_identify_car()

        elif self.state == SortState.ROUTE_SWITCHES:
            self.state_route_switches()

        elif self.state == SortState.MOVE_TO_TRACK:
            self.state_move_to_track()

        elif self.state == SortState.DECOUPLE:
            self.state_decouple()

        elif self.state == SortState.PULL_OUT:
            self.state_pull_out()

        elif self.state == SortState.NEXT_CAR:
            self.state_next_car()

        elif self.state == SortState.COMPLETE:
            self.state_complete()

        elif self.state == SortState.ABORTED:
            self.stop_sorting()

    def state_wait_for_rfid(self):
        self.log("[STATE] WAIT_FOR_RFID")

        detections = self.rfid.scan_all()

        if not detections:
            return

        for reader_name, data in detections.items():
            car_name = data["car"]

            if car_name:
                self.current_reader = reader_name
                self.current_tag = data["tag"]
                self.current_car = car_name
                self.state = SortState.IDENTIFY_CAR
                return

        self.log("[RFID] Unknown tag detected")

    def state_identify_car(self):
        self.log(
            f"[STATE] IDENTIFY_CAR: {self.current_car} "
            f"at {self.current_reader}"
        )

        if self.current_car not in self.consist:
            self.log(f"[WARN] {self.current_car} already sorted or not in consist")
            self.state = SortState.WAIT_FOR_RFID
            return

        self.current_target_track = self.car_destinations[self.current_car]

        self.log(
            f"[SORT] {self.current_car} destination = "
            f"Track {self.current_target_track}"
        )

        self.state = SortState.ROUTE_SWITCHES

    def state_route_switches(self):
        self.log("[STATE] ROUTE_SWITCHES")

        self.io.route_to_track(self.current_target_track)

        self.state = SortState.MOVE_TO_TRACK

    def state_move_to_track(self):
        self.log("[STATE] MOVE_TO_TRACK")

        self.io.set_crossing(True)

        self.loco_forward(APPROACH_SPEED)
        time.sleep(APPROACH_SEC)
        self.loco_stop()

        self.loco_reverse(BACK_IN_SPEED)
        time.sleep(BACK_IN_SEC)
        self.loco_stop()

        self.state = SortState.DECOUPLE

    def state_decouple(self):
        self.log("[STATE] DECOUPLE")

        time.sleep(DECOUPLE_SETTLE_SEC)
        self.io.decouple()

        self.state = SortState.PULL_OUT

    def state_pull_out(self):
        self.log("[STATE] PULL_OUT")

        self.loco_forward(PULL_OUT_SPEED)
        time.sleep(PULL_OUT_SEC)
        self.loco_stop()

        self.io.set_crossing(False)
        self.io.set_all_default()

        self.state = SortState.NEXT_CAR

    def state_next_car(self):
        self.log("[STATE] NEXT_CAR")

        if self.current_car in self.consist:
            self.consist.remove(self.current_car)
            self.track_contents[self.current_target_track].append(self.current_car)

        self.log(
            f"[SORT] Dropped {self.current_car} "
            f"onto Track {self.current_target_track}"
        )

        self.current_car = None
        self.current_reader = None
        self.current_tag = None
        self.current_target_track = None

        self.show_state()

        if len(self.consist) == 0:
            self.state = SortState.COMPLETE
        else:
            self.state = SortState.WAIT_FOR_RFID

    def state_complete(self):
        self.log("[STATE] COMPLETE")
        self.log("[SYSTEM] Sorting complete")

        self.loco_stop()
        self.io.set_all_default()

        self.running = False
        self.state = SortState.IDLE

    # -------------------------------------------------
    # Stop / reset
    # -------------------------------------------------
    def stop_sorting(self):
        self.running = False
        self.state = SortState.ABORTED

        self.loco_stop()
        self.io.set_crossing(False)
        self.io.set_all_default()

        self.log("[SYSTEM] Stop requested")

    def reset_system(self):
        self.stop_sorting()

        self.state = SortState.IDLE
        self.consist = list(self.initial_consist)

        self.track_contents = {
            1: [],
            2: [],
            3: [],
            4: [],
        }

        self.current_car = None
        self.current_reader = None
        self.current_tag = None
        self.current_target_track = None

        self.io.set_all_default()

        self.log("[SYSTEM] Reset complete")
        self.show_state()

    # -------------------------------------------------
    # Manual helpers
    # -------------------------------------------------
    def manual_route_track(self, track):
        self.io.route_to_track(track)

    def manual_decouple(self):
        self.io.decouple()

    def show_state(self):
        self.log(f"[STATE] Machine state: {self.state.name}")
        self.log(f"[STATE] Remaining consist: {self.consist}")
        self.log(f"[STATE] Track contents: {self.track_contents}")
        self.log(f"[STATE] Destinations: {self.car_destinations}")