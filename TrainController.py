# TrainController.py
import threading
import time
import train_config
from TrainIO import TrainIO
from TrainRFID import TrainRFID
from TrainTrack import TrainTrack

DROP_CONFIRM_TIMEOUT = 30.0   # seconds to wait for track RFID before giving up


class TrainController:
    def __init__(self, logger=print):
        self.logger = logger
        self.io    = TrainIO(logger=self.log)
        self.rfid  = TrainRFID(logger=self.log)
        self.track = TrainTrack(logger=self.log)

        # Consist: ordered front→back as scanned by entry reader
        self.car_order: list = []

        # Destinations: car_name → track (1–3)
        self.car_destinations: dict = {
            name: info["default_track"]
            for name, info in train_config.CAR_ROSTER.items()
        }

        # What's parked on each siding
        self.track_contents: dict = {1: None, 2: None, 3: None}

        # GUI callbacks — set these from the GUI after construction
        self.on_car_scanned   = None   # (car_name)
        self.on_status_change = None   # (status_str)
        self.on_drop_confirmed = None  # (car_name, track)

        self._scanning = False
        self._waiting_for_confirm = False
        self._manual_confirm_event = threading.Event()
        self._scan_thread = None
        self._sort_thread = None

    def log(self, msg):
        self.logger(msg)

    def _set_status(self, msg):
        self.log(f"[STATUS] {msg}")
        if self.on_status_change:
            self.on_status_change(msg)

    # ── Car roster ────────────────────────────────────────────────────────────

    def register_car(self, name, uid, default_track):
        if default_track not in (1, 2, 3):
            self.log(f"[WARN] Track must be 1–3")
            return False
        uid = uid.upper().strip()
        train_config.CAR_ROSTER[name] = {"rfid": uid, "default_track": default_track}
        train_config.save_roster(train_config.CAR_ROSTER)
        self.car_destinations[name] = default_track
        self.log(f"[CFG] Registered {name}: UID={uid} Track={default_track}")
        return True

    def set_destination(self, car_name, track):
        if track not in (1, 2, 3):
            self.log(f"[WARN] Invalid track {track}")
            return
        self.car_destinations[car_name] = track
        if car_name in train_config.CAR_ROSTER:
            train_config.CAR_ROSTER[car_name]["default_track"] = track
            train_config.save_roster(train_config.CAR_ROSTER)
        self.log(f"[CFG] {car_name} → Track {track}")

    # ── Entry scan (Step 1) ───────────────────────────────────────────────────

    def start_entry_scan(self):
        if self._scanning:
            return
        self.car_order = []
        self._scanning = True
        self._scan_thread = threading.Thread(target=self._entry_scan_loop, daemon=True)
        self._scan_thread.start()
        self._set_status("Scanning — drive train past entry reader...")

    def stop_entry_scan(self):
        self._scanning = False
        self._set_status(f"Scan complete. {len(self.car_order)} car(s) detected.")

    def _entry_scan_loop(self):
        last_uid   = None
        last_time  = 0.0
        DEBOUNCE   = 2.0

        while self._scanning:
            uid = self.rfid.scan_reader(
                train_config.ENTRY_READER_IDX, timeout_sec=0.3
            )
            if uid:
                now = time.time()
                if uid != last_uid or (now - last_time) > DEBOUNCE:
                    car = self.rfid.identify_car(uid)
                    if car and car not in self.car_order:
                        self.car_order.append(car)
                        self.log(f"[SCAN] Detected {car} (position {len(self.car_order)})")
                        if self.on_car_scanned:
                            self.on_car_scanned(car)
                    elif not car:
                        self.log(f"[SCAN] Unknown tag {uid} — register it first")
                    last_uid  = uid
                    last_time = now
            time.sleep(0.05)

    def clear_consist(self):
        self.car_order = []
        self._set_status("Consist cleared.")

    # ── Sorting (Step 3) ──────────────────────────────────────────────────────

    @property
    def next_car(self):
        """The last car in the consist — the one at the back of the train."""
        return self.car_order[-1] if self.car_order else None

    def fire_switch_for_next_car(self):
        """
        Set the switch for the next car to drop and start waiting for
        track-end RFID confirmation in a background thread.
        """
        car = self.next_car
        if not car:
            self._set_status("No cars left in consist.")
            return

        track = self.car_destinations.get(car)
        if not track:
            self._set_status(f"No destination set for {car}.")
            return

        self.io.route_to_track(track)
        self._set_status(
            f"Switch set → Track {track} for {car}\n"
            f"Reverse train into Track {track}, then pull forward."
        )

        self._manual_confirm_event.clear()
        self._waiting_for_confirm = True
        self._sort_thread = threading.Thread(
            target=self._wait_for_drop, args=(car, track), daemon=True
        )
        self._sort_thread.start()

    def _wait_for_drop(self, car_name, track):
        reader_idx = train_config.TRACK_READER_IDX[track]
        car_uid    = train_config.CAR_ROSTER.get(car_name, {}).get("rfid", "")
        deadline   = time.time() + DROP_CONFIRM_TIMEOUT

        while time.time() < deadline:
            if self._manual_confirm_event.is_set():
                self.log(f"[SORT] Manual confirm for {car_name}")
                self._finish_drop(car_name, track)
                return

            uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.3)
            if uid and uid.upper() == car_uid.upper():
                self.log(f"[SORT] RFID confirmed {car_name} at Track {track}")
                self._finish_drop(car_name, track)
                return

        # Timeout
        self._waiting_for_confirm = False
        self._set_status(
            f"Timeout waiting for {car_name} at Track {track}.\n"
            f"Click Manual Confirm if car was dropped, or retry."
        )

    def _finish_drop(self, car_name, track):
        self._waiting_for_confirm = False
        self.io.set_all_straight()
        if car_name in self.car_order:
            self.car_order.remove(car_name)
        self.track_contents[track] = car_name
        if self.on_drop_confirmed:
            self.on_drop_confirmed(car_name, track)
        remaining = len(self.car_order)
        if remaining:
            self._set_status(
                f"{car_name} dropped at Track {track} ✓\n"
                f"{remaining} car(s) remaining — click 'Fire Switch' for next car."
            )
        else:
            self._set_status("All cars sorted!")

    def manual_confirm_drop(self):
        """Called by GUI button if RFID doesn't detect the drop."""
        self._manual_confirm_event.set()

    def skip_car(self):
        """Remove the last car from the consist without dropping it."""
        if self.car_order:
            skipped = self.car_order.pop()
            self.io.set_all_straight()
            self._set_status(f"Skipped {skipped}. Next: {self.next_car or 'none'}.")

    def reset(self):
        self._scanning = False
        self._waiting_for_confirm = False
        self._manual_confirm_event.set()   # unblock any waiting thread
        self.car_order = []
        self.track_contents = {1: None, 2: None, 3: None}
        self.io.set_all_straight()
        self._set_status("Reset. Ready to scan.")

    # ── Manual controls ───────────────────────────────────────────────────────

    def manual_pulse(self, switch_name, direction):
        self.io._pulse(switch_name, direction)
        self.log(f"[MANUAL] Pulsed {switch_name} {direction}")

    def manual_all_straight(self):
        self.io.set_all_straight()

    def test_reader(self, reader_idx):
        uid = self.rfid.scan_reader(reader_idx, timeout_sec=3.0)
        name = train_config.RFID_READERS[reader_idx]["name"]
        if uid:
            car = self.rfid.identify_car(uid)
            self.log(f"[TEST] {name}: {uid} → {car or 'unregistered'}")
        else:
            self.log(f"[TEST] {name}: no tag detected")

    def show_state(self):
        self.log(f"[STATE] Consist:        {self.car_order}")
        self.log(f"[STATE] Track contents: {self.track_contents}")
        self.log(f"[STATE] Destinations:   {self.car_destinations}")

    def shutdown(self):
        self._scanning = False
        self._manual_confirm_event.set()
        try:
            self.track.cleanup()
        except Exception as e:
            self.log(f"[WARN] Track cleanup: {e}")
        try:
            self.io.cleanup()
        except Exception as e:
            self.log(f"[WARN] IO cleanup: {e}")
        try:
            self.rfid.cleanup()
        except Exception as e:
            self.log(f"[WARN] RFID cleanup: {e}")
