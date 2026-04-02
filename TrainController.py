# TrainController.py

import time
from train_config import (
    CAR_ROSTER,
    DEFAULT_CONSIST_ORDER,
    LOCO_ADDRESS,
    APPROACH_SEC,
    BACK_IN_SEC,
    DECOUPLE_SETTLE_SEC,
    PULL_OUT_SEC,
    RETURN_TO_LOOP_SEC,
    APPROACH_SPEED,
    BACK_IN_SPEED,
    PULL_OUT_SPEED,
    VICTORY_LAP_SPEED,
)
from TrainIO import TrainIO
from TrainRFID import TrainRFID


class TrainController:
    """
    Consist-aware sorter for this layout.
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.io = TrainIO(logger=self.log)
        self.rfid = TrainRFID(logger=self.log)
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

        self.current_speed = 0
        self.current_direction_forward = True

    def log(self, msg: str):
        self.logger(msg)

    def set_destination(self, car_name: str, track: int):
        if car_name not in self.car_destinations:
            self.log(f"[WARN] Unknown car: {car_name}")
            return
        if track not in [1, 2, 3, 4]:
            self.log(f"[WARN] Invalid destination track: {track}")
            return
        self.car_destinations[car_name] = track
        self.log(f"[CFG] {car_name} -> Track {track}")

    def set_consist_order(self, cars):
        valid_cars = sorted(DEFAULT_CONSIST_ORDER)
        if sorted(cars) != valid_cars:
            self.log("[WARN] Invalid consist order ignored")
            return
        self.initial_consist = list(cars)
        self.consist = list(cars)
        self.log(f"[CFG] Consist order set to: {self.consist}")

    def show_state(self):
        self.log(f"[STATE] Remaining consist: {self.consist}")
        self.log(f"[STATE] Track contents: {self.track_contents}")
        self.log(f"[STATE] Destinations: {self.car_destinations}")

    def get_next_car_to_drop(self):
        if not self.consist:
            return None
        return self.consist[0]

    def loco_stop(self):
        self.current_speed = 0
        self.io.dcc_loco_speed(LOCO_ADDRESS, 0, self.current_direction_forward)
        self.log("[LOCO] Stop")

    def loco_forward(self, speed: int):
        self.current_speed = speed
        self.current_direction_forward = True
        self.io.dcc_loco_speed(LOCO_ADDRESS, speed, True)
        self.log(f"[LOCO] Forward speed {speed}")

    def loco_reverse(self, speed: int):
        self.current_speed = speed
        self.current_direction_forward = False
        self.io.dcc_loco_speed(LOCO_ADDRESS, speed, False)
        self.log(f"[LOCO] Reverse speed {speed}")

    # -----------------------------
    # RFID + DCC test helpers
    # -----------------------------
    def scan_rfid_once(self):
        tag = self.rfid.read_tag(timeout_sec=1.0)
        if not tag:
            self.log("[RFID] No tag detected")
            return None

        car_name = self.rfid.identify_car(tag)
        if not car_name:
            self.log(f"[RFID] Unknown tag detected: {tag}")
            return tag

        track = self.car_destinations[car_name]
        self.log(f"[RFID] Tag {tag} -> {car_name} -> destination Track {track}")
        return tag

    def scan_and_prepare_route(self):
        tag = self.rfid.read_tag(timeout_sec=1.0)
        if not tag:
            self.log("[RFID] No tag detected")
            return

        car_name = self.rfid.identify_car(tag)
        if not car_name:
            self.log(f"[RFID] Unknown tag detected: {tag}")
            return

        target_track = self.car_destinations[car_name]
        self.log(f"[RFID] Tag {tag} -> {car_name} -> Track {target_track}")
        self.io.route_to_track(target_track)
        self.log("[TEST] Route set from RFID result")

    def dcc_test_idle(self):
        self.io.dcc_idle()
        self.log("[TEST] Sent DCC idle packet")

    def dcc_test_forward(self):
        self.loco_forward(APPROACH_SPEED)
        self.log("[TEST] Sent DCC forward command")

    def dcc_test_reverse(self):
        self.loco_reverse(BACK_IN_SPEED)
        self.log("[TEST] Sent DCC reverse command")

    def dcc_test_stop(self):
        self.loco_stop()
        self.log("[TEST] Sent DCC stop command")

    # -----------------------------
    # Existing automated flow
    # -----------------------------
    def send_loco_to_victory_lap(self):
        self.log("[SEQ] Sending locomotive to Victory Lap")
        self.io.route_to_victory_lap()
        self.loco_forward(VICTORY_LAP_SPEED)
        time.sleep(RETURN_TO_LOOP_SEC)
        self.loco_stop()
        self.io.route_to_main_from_loop()
        self.log("[SEQ] Locomotive reached Victory Lap staging area")

    def perform_dropoff_sequence(self, car_name: str, target_track: int):
        self.log(f"[SEQ] Begin dropoff: {car_name} -> Track {target_track}")

        if not self.running:
            self.log("[SEQ] Aborted before start")
            return False

        self.io.route_to_main_from_loop()
        self.io.set_crossing(True)
        self.loco_forward(APPROACH_SPEED)
        time.sleep(APPROACH_SEC)
        self.loco_stop()

        if not self.running:
            self.io.set_crossing(False)
            self.io.set_all_default()
            self.log("[SEQ] Aborted after approach")
            return False

        self.io.route_to_track(target_track)

        self.loco_reverse(BACK_IN_SPEED)
        time.sleep(BACK_IN_SEC)
        self.loco_stop()

        if not self.running:
            self.io.set_crossing(False)
            self.io.set_all_default()
            self.log("[SEQ] Aborted after back-in")
            return False

        time.sleep(DECOUPLE_SETTLE_SEC)
        self.io.decouple()

        if not self.running:
            self.io.set_crossing(False)
            self.io.set_all_default()
            self.log("[SEQ] Aborted after decouple")
            return False

        self.loco_forward(PULL_OUT_SPEED)
        time.sleep(PULL_OUT_SEC)
        self.loco_stop()

        self.io.set_crossing(False)
        self.io.set_all_default()

        self.log(f"[SEQ] Dropoff complete: {car_name}")
        return True

    def sort_next_car(self):
        car_name = self.get_next_car_to_drop()
        if car_name is None:
            self.log("[SORT] No cars left to sort")
            return False

        target_track = self.car_destinations[car_name]
        self.log(f"[SORT] Next car: {car_name}, destination Track {target_track}")

        completed = self.perform_dropoff_sequence(car_name, target_track)
        if not completed:
            self.log("[SORT] Dropoff did not complete")
            return False

        dropped_car = self.consist.pop(0)
        self.track_contents[target_track].append(dropped_car)

        self.log(f"[SORT] Dropped {dropped_car} onto Track {target_track}")
        self.show_state()
        return True

    def start_sorting(self):
        self.running = True
        self.log("[SYSTEM] Start automated sorting")
        self.show_state()

        while self.running and len(self.consist) > 0:
            ok = self.sort_next_car()
            if not ok:
                break

        self.loco_stop()
        self.io.set_all_default()
        self.log("[SYSTEM] Sorting run complete")
        self.show_state()

        if self.running:
            self.send_loco_to_victory_lap()

    def stop_sorting(self):
        self.running = False
        self.loco_stop()
        self.io.set_crossing(False)
        self.io.set_all_default()
        self.log("[SYSTEM] Stop requested")

    def reset_system(self):
        self.stop_sorting()
        self.consist = list(self.initial_consist)
        self.track_contents = {
            1: [],
            2: [],
            3: [],
            4: [],
        }
        self.io.set_all_default()
        self.log("[SYSTEM] Reset complete")
        self.show_state()

    def manual_route_track(self, track: int):
        self.io.route_to_track(track)

    def manual_decouple(self):
        self.io.decouple()

    def manual_send_to_victory_lap(self):
        self.send_loco_to_victory_lap()