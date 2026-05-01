# TrainController.py
import threading
import time
import train_config
from TrainIO import TrainIO
from TrainRFID import TrainRFID


class TrainController:
    def __init__(self, logger=print):
        self.logger = logger
        self.io = TrainIO(logger=self.log)
        self.rfid = TrainRFID(logger=self.log)

        # car_name → destination track (1–3)
        self.car_destinations: dict = {
            name: info["default_track"]
            for name, info in train_config.CAR_ROSTER.items()
        }

        self._auto_scan = False
        self._auto_thread = None

    def log(self, msg: str):
        self.logger(msg)

    # ── Car roster ────────────────────────────────────────────────────────────

    def register_car(self, name: str, uid: str, default_track: int) -> bool:
        if default_track not in (1, 2, 3):
            self.log(f"[WARN] Track must be 1–3, got {default_track}")
            return False
        uid = uid.upper().strip()
        if not uid:
            self.log("[WARN] Empty UID; skipped")
            return False
        train_config.CAR_ROSTER[name] = {"rfid": uid, "default_track": default_track}
        train_config.save_roster(train_config.CAR_ROSTER)
        self.car_destinations[name] = default_track
        self.log(f"[CFG] Registered {name}: UID={uid}, Track={default_track}")
        return True

    def unregister_car(self, name: str):
        train_config.CAR_ROSTER.pop(name, None)
        train_config.save_roster(train_config.CAR_ROSTER)
        self.car_destinations.pop(name, None)
        self.log(f"[CFG] Removed {name}")

    def set_destination(self, car_name: str, track: int):
        if car_name not in self.car_destinations:
            self.log(f"[WARN] Unknown car: {car_name}")
            return
        if track not in (1, 2, 3):
            self.log(f"[WARN] Invalid track: {track}")
            return
        self.car_destinations[car_name] = track
        if car_name in train_config.CAR_ROSTER:
            train_config.CAR_ROSTER[car_name]["default_track"] = track
            train_config.save_roster(train_config.CAR_ROSTER)
        self.log(f"[CFG] {car_name} → Track {track}")

    def show_state(self):
        self.log(f"[STATE] Destinations: {self.car_destinations}")
        self.log(f"[STATE] Roster size:  {len(train_config.CAR_ROSTER)} cars")

    # ── Manual switch control ─────────────────────────────────────────────────

    def manual_route_track(self, track: int):
        self.io.route_to_track(track)

    def manual_route_main(self):
        self.io.set_all_straight()

    # ── RFID scan helpers ─────────────────────────────────────────────────────

    def scan_once(self):
        """Scan all readers once (3 s timeout). Log result; return (reader_idx, uid)."""
        reader_idx, uid = self.rfid.scan_all(timeout_sec=3.0)
        if uid is None:
            self.log("[RFID] No tag detected")
            return (None, None)
        reader_name = train_config.RFID_READERS[reader_idx]["name"]
        car = self.rfid.identify_car(uid)
        if car:
            track = self.car_destinations.get(car, "?")
            self.log(f"[RFID] {reader_name}: {uid} → {car} → Track {track}")
        else:
            self.log(f"[RFID] {reader_name}: {uid} (unregistered)")
        return (reader_idx, uid)

    def scan_and_route(self):
        """Scan, identify, and immediately fire the correct switch."""
        reader_idx, uid = self.rfid.scan_all(timeout_sec=3.0)
        if uid is None:
            self.log("[RFID] No tag detected")
            return
        car = self.rfid.identify_car(uid)
        if not car:
            self.log(f"[RFID] Unknown tag: {uid}")
            return
        track = self.car_destinations[car]
        self.log(f"[RFID] {uid} → {car} → routing Track {track}")
        self.io.route_to_track(track)

    # ── Auto-scan mode ────────────────────────────────────────────────────────

    def start_auto_scan(self):
        """
        Continuously poll all readers. When a registered tag is detected,
        automatically fire the switch for that car's destination track.
        """
        if self._auto_scan:
            self.log("[AUTO] Already running")
            return
        self._auto_scan = True
        self._auto_thread = threading.Thread(target=self._auto_scan_loop, daemon=True)
        self._auto_thread.start()
        self.log("[AUTO] Auto-scan started")

    def stop_auto_scan(self):
        self._auto_scan = False
        self.log("[AUTO] Auto-scan stopped")

    def _auto_scan_loop(self):
        last_uid = None
        last_uid_time = 0.0
        DEBOUNCE_SEC = 2.0   # ignore the same tag for 2 s after routing

        while self._auto_scan:
            reader_idx, uid = self.rfid.scan_all(timeout_sec=0.3)
            if uid:
                now = time.time()
                if uid == last_uid and (now - last_uid_time) < DEBOUNCE_SEC:
                    time.sleep(0.05)
                    continue
                car = self.rfid.identify_car(uid)
                reader_name = train_config.RFID_READERS[reader_idx]["name"]
                if car:
                    track = self.car_destinations.get(car)
                    if track:
                        self.log(f"[AUTO] {reader_name}: {uid} → {car} → Track {track}")
                        self.io.route_to_track(track)
                        last_uid = uid
                        last_uid_time = time.time()
                else:
                    self.log(f"[AUTO] {reader_name}: {uid} (unregistered — ignored)")
            time.sleep(0.05)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def shutdown(self):
        self.stop_auto_scan()
        try:
            self.io.cleanup()
        except Exception as e:
            self.log(f"[WARN] IO cleanup: {e}")
        try:
            self.rfid.cleanup()
        except Exception as e:
            self.log(f"[WARN] RFID cleanup: {e}")
