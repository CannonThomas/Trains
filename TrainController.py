# TrainController.py
import threading
import time
import train_config
from train_config import (
    CAR_ROSTER,
    LOCO_ADDRESS,
    APPROACH_SEC, BACK_IN_SEC, DECOUPLE_SETTLE_SEC, PULL_OUT_SEC, RETURN_TO_LOOP_SEC,
    APPROACH_SPEED, BACK_IN_SPEED, PULL_OUT_SPEED, VICTORY_LAP_SPEED,
)
from TrainIO import TrainIO
from TrainRFID import TrainRFID


class TrainController:
    def __init__(self, logger=print):
        self.logger = logger
        self.io = TrainIO(logger=self.log)
        self.rfid = TrainRFID(logger=self.log)
        self.running = False
        self._sort_thread = None

        # Destinations: car_name → track (1–3)
        self.car_destinations: dict = {
            name: info["default_track"]
            for name, info in CAR_ROSTER.items()
        }

        # Consist: ordered list of car names currently coupled to the locomotive
        self.consist: list = list(CAR_ROSTER.keys())

        # Contents of each siding track after drops
        self.track_contents: dict = {1: [], 2: [], 3: []}

        self.current_speed = 0
        self.current_direction_forward = True

    def log(self, msg: str):
        self.logger(msg)

    # ── Car roster management ─────────────────────────────────────────────────

    def register_car(self, name: str, uid: str, default_track: int) -> bool:
        """Register (or update) a car. Persists to car_roster.json."""
        if default_track not in (1, 2, 3):
            self.log(f"[WARN] Invalid track {default_track}; must be 1–3")
            return False
        uid = uid.upper().strip()
        if not uid:
            self.log("[WARN] Empty UID; registration skipped")
            return False

        train_config.CAR_ROSTER[name] = {"rfid": uid, "default_track": default_track}
        train_config.save_roster(train_config.CAR_ROSTER)

        self.car_destinations[name] = default_track
        if name not in self.consist:
            self.consist.append(name)

        self.log(f"[CFG] Registered {name}: UID={uid}, Track={default_track}")
        return True

    def unregister_car(self, name: str):
        """Remove a car from the roster and consist."""
        train_config.CAR_ROSTER.pop(name, None)
        train_config.save_roster(train_config.CAR_ROSTER)
        self.car_destinations.pop(name, None)
        if name in self.consist:
            self.consist.remove(name)
        self.log(f"[CFG] Removed {name}")

    # ── Destination / consist config ──────────────────────────────────────────

    def set_destination(self, car_name: str, track: int):
        if car_name not in self.car_destinations:
            self.log(f"[WARN] Unknown car: {car_name}")
            return
        if track not in (1, 2, 3):
            self.log(f"[WARN] Invalid destination track: {track}")
            return
        self.car_destinations[car_name] = track
        if car_name in train_config.CAR_ROSTER:
            train_config.CAR_ROSTER[car_name]["default_track"] = track
            train_config.save_roster(train_config.CAR_ROSTER)
        self.log(f"[CFG] {car_name} → Track {track}")

    def set_consist_order(self, cars: list):
        roster_names = set(train_config.CAR_ROSTER.keys())
        if not all(c in roster_names for c in cars):
            self.log("[WARN] Consist contains unregistered car name(s); ignored")
            return
        self.consist = list(cars)
        self.log(f"[CFG] Consist order: {self.consist}")

    def show_state(self):
        self.log(f"[STATE] Consist remaining: {self.consist}")
        self.log(f"[STATE] Track contents:    {self.track_contents}")
        self.log(f"[STATE] Destinations:      {self.car_destinations}")

    # ── Locomotive motion ─────────────────────────────────────────────────────

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

    # ── RFID test helpers ─────────────────────────────────────────────────────

    def scan_rfid_once(self):
        """Scan all readers once; log and return (reader_idx, uid) or (None, None)."""
        reader_idx, uid = self.rfid.scan_all(timeout_sec=3.0)
        if uid is None:
            self.log("[RFID] No tag detected")
            return (None, None)

        car_name = self.rfid.identify_car(uid)
        reader_name = train_config.RFID_READERS[reader_idx]["name"]
        if car_name:
            track = self.car_destinations.get(car_name, "?")
            self.log(f"[RFID] {reader_name}: {uid} → {car_name} → Track {track}")
        else:
            self.log(f"[RFID] {reader_name}: {uid} (unregistered)")
        return (reader_idx, uid)

    def scan_and_prepare_route(self):
        """Scan, identify, and set the track switch for the detected car."""
        reader_idx, uid = self.rfid.scan_all(timeout_sec=3.0)
        if uid is None:
            self.log("[RFID] No tag detected")
            return

        car_name = self.rfid.identify_car(uid)
        if not car_name:
            self.log(f"[RFID] Unknown tag: {uid}")
            return

        track = self.car_destinations[car_name]
        self.log(f"[RFID] {uid} → {car_name} → Track {track}")
        self.io.route_to_track(track)
        self.log("[TEST] Route set from RFID scan")

    # ── DCC test helpers ──────────────────────────────────────────────────────

    def dcc_test_idle(self):
        self.io.dcc_idle()
        self.log("[TEST] DCC idle")

    def dcc_test_forward(self):
        self.loco_forward(APPROACH_SPEED)

    def dcc_test_reverse(self):
        self.loco_reverse(BACK_IN_SPEED)

    def dcc_test_stop(self):
        self.loco_stop()

    # ── Sorting sequences ─────────────────────────────────────────────────────

    def send_loco_to_victory_lap(self):
        self.log("[SEQ] Sending locomotive to Victory Lap")
        self.io.set_all_default()      # all switches straight → enters the loop
        self.loco_forward(VICTORY_LAP_SPEED)
        time.sleep(RETURN_TO_LOOP_SEC)
        self.loco_stop()
        self.log("[SEQ] Locomotive in Victory Lap staging area")

    def perform_dropoff_sequence(self, car_name: str, target_track: int) -> bool:
        self.log(f"[SEQ] Dropoff start: {car_name} → Track {target_track}")

        if not self.running:
            self.log("[SEQ] Aborted before start")
            return False

        # Approach: all switches straight, move forward past the switches
        self.io.set_all_default()
        self.io.set_crossing(True)
        self.loco_forward(APPROACH_SPEED)
        time.sleep(APPROACH_SEC)
        self.loco_stop()

        if not self.running:
            self.io.set_crossing(False)
            self.io.set_all_default()
            self.log("[SEQ] Aborted after approach")
            return False

        # Set the target switch (and any preceding switches to straight)
        self.io.route_to_track(target_track)

        # Back into the siding
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

        # Pull out forward
        self.loco_forward(PULL_OUT_SPEED)
        time.sleep(PULL_OUT_SEC)
        self.loco_stop()

        self.io.set_crossing(False)
        self.io.set_all_default()
        self.log(f"[SEQ] Dropoff complete: {car_name}")
        return True

    def sort_next_car(self) -> bool:
        if not self.consist:
            self.log("[SORT] No cars left to sort")
            return False

        car_name = self.consist[0]
        target_track = self.car_destinations.get(car_name, 1)
        self.log(f"[SORT] Next: {car_name} → Track {target_track}")

        if not self.perform_dropoff_sequence(car_name, target_track):
            self.log("[SORT] Dropoff did not complete")
            return False

        dropped = self.consist.pop(0)
        self.track_contents[target_track].append(dropped)
        self.log(f"[SORT] Dropped {dropped} onto Track {target_track}")
        self.show_state()
        return True

    def start_sorting(self):
        if self.running:
            self.log("[SYSTEM] Already running")
            return

        self.running = True
        self.log("[SYSTEM] Automated sorting started")
        self.show_state()

        while self.running and self.consist:
            if not self.sort_next_car():
                break

        self.loco_stop()
        self.io.set_all_default()
        self.log("[SYSTEM] Sorting run complete")
        self.show_state()

        if self.running:
            self.send_loco_to_victory_lap()

        self.running = False

    def start_sorting_async(self):
        if self._sort_thread and self._sort_thread.is_alive():
            self.log("[SYSTEM] Sorting already running")
            return
        self._sort_thread = threading.Thread(target=self.start_sorting, daemon=True)
        self._sort_thread.start()

    def stop_sorting(self):
        self.running = False
        self.loco_stop()
        self.io.set_crossing(False)
        self.io.set_all_default()
        self.log("[SYSTEM] Stop requested")

    def reset_system(self):
        self.stop_sorting()
        self.consist = list(train_config.CAR_ROSTER.keys())
        self.car_destinations = {
            name: info["default_track"]
            for name, info in train_config.CAR_ROSTER.items()
        }
        self.track_contents = {1: [], 2: [], 3: []}
        self.io.set_all_default()
        self.log("[SYSTEM] Reset complete")
        self.show_state()

    # ── Manual controls ───────────────────────────────────────────────────────

    def manual_route_track(self, track: int):
        self.io.route_to_track(track)

    def manual_route_main(self):
        self.io.set_all_default()

    def manual_decouple(self):
        self.io.decouple()

    def manual_send_to_victory_lap(self):
        self.send_loco_to_victory_lap()

    def shutdown(self):
        self.stop_sorting()
        try:
            self.io.cleanup()
        except Exception as e:
            self.log(f"[WARN] Cleanup failed: {e}")
        try:
            self.rfid.cleanup()
        except Exception as e:
            self.log(f"[WARN] RFID cleanup failed: {e}")
