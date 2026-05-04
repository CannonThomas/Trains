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

        # Live track monitor — polls track-end readers in the background
        self._monitor_running = False
        self._monitor_thread = None
        self._monitor_pause = False  # set True during sort/scan/autonomous

        # Autonomous routine state
        self._auto_running = False
        self._auto_thread = None
        self._auto_abort = False

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
            if car and reader_idx in (1, 2, 3):
                track = reader_idx
                self.track_contents[track] = car
                if self.on_drop_confirmed:
                    self.on_drop_confirmed(car, track)
        else:
            self.log(f"[TEST] {name}: no tag detected")
            # Clear the track box if this is a track-end reader
            if reader_idx in (1, 2, 3):
                track = reader_idx
                self.track_contents[track] = None
                if self.on_drop_confirmed:
                    self.on_drop_confirmed(None, track)

    # ── Live Track Monitor ────────────────────────────────────────────────────

    def start_track_monitor(self):
        if self._monitor_running:
            return
        self._monitor_running = True
        self._monitor_thread = threading.Thread(
            target=self._track_monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.log("[MON] Live track monitor started")

    def stop_track_monitor(self):
        self._monitor_running = False
        self.log("[MON] Live track monitor stopped")

    def _track_monitor_loop(self):
        # Track which car each track currently shows so we only fire callbacks on change
        last_state = {1: "<init>", 2: "<init>", 3: "<init>"}
        while self._monitor_running:
            try:
                if (self._monitor_pause or self._scanning or
                        self._waiting_for_confirm or self._auto_running):
                    time.sleep(0.3)
                    continue
                for track in (1, 2, 3):
                    if not self._monitor_running:
                        break
                    reader_idx = train_config.TRACK_READER_IDX[track]
                    try:
                        uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.20)
                    except Exception as e:
                        self.log(f"[MON] reader {track} err: {e}")
                        uid = None
                    car = self.rfid.identify_car(uid) if uid else None
                    if car != last_state[track]:
                        last_state[track] = car
                        self.track_contents[track] = car
                        if self.on_drop_confirmed:
                            self.on_drop_confirmed(car, track)
                    time.sleep(0.05)
                time.sleep(0.3)
            except Exception as e:
                self.log(f"[MON] loop err: {e}")
                time.sleep(1.0)

    # ── Autonomous routine ────────────────────────────────────────────────────

    def start_autonomous(self, pickup_order):
        """Run the full autonomous pickup→sort cycle.
        pickup_order: list of track numbers in the order to pick up cars."""
        if self._auto_running:
            self.log("[AUTO] already running")
            return
        valid = [t for t in pickup_order if t in (1, 2, 3)]
        if not valid:
            self.log("[AUTO] no valid pickup tracks")
            return
        self._auto_abort = False
        self._auto_running = True
        self._auto_thread = threading.Thread(
            target=self._autonomous_loop, args=(valid,), daemon=True)
        self._auto_thread.start()

    def abort_autonomous(self):
        self._auto_abort = True
        self.log("[AUTO] abort requested")

    # ── Autonomous helpers ────────────────────────────────────────────────────

    def _drive_until_rfid(self, reader_idx, direction, speed, timeout=30.0,
                          expected_car=None):
        """Drive in given direction at speed until reader detects a tag.
        If expected_car set, wait for that specific car. Returns True if hit."""
        self.track.set_direction(direction)
        self.track.set_speed(speed)
        deadline = time.time() + timeout
        while time.time() < deadline and not self._auto_abort:
            uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.15)
            if uid:
                car = self.rfid.identify_car(uid)
                if expected_car is None or car == expected_car:
                    return True
            time.sleep(0.05)
        return False

    def _wait_track_state(self, track, want_car, timeout=30.0):
        """Wait until track-end RFID matches want_car (None = empty)."""
        reader_idx = train_config.TRACK_READER_IDX[track]
        deadline = time.time() + timeout
        while time.time() < deadline and not self._auto_abort:
            uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.20)
            car = self.rfid.identify_car(uid) if uid else None
            self.track_contents[track] = car
            if self.on_drop_confirmed:
                self.on_drop_confirmed(car, track)
            if car == want_car:
                return True
            time.sleep(0.10)
        return False

    def _autonomous_loop(self, pickup_order):
        try:
            self._set_status("AUTO: starting pickup phase")
            self.io.set_all_straight()
            time.sleep(0.5)

            picked_up = []  # cars picked up, in pickup order (front of train = first)

            # ── Phase 1: PICKUP ───────────────────────────────────────────
            for track in pickup_order:
                if self._auto_abort:
                    break
                car_at_track = self.track_contents.get(track)
                self._set_status(f"AUTO: picking up Track {track}"
                                 + (f" ({car_at_track})" if car_at_track else ""))

                # 1. Drive FWD until entry RFID hit
                self.log(f"[AUTO] driving FWD to entry reader")
                self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                       "FWD", speed=50, timeout=30)
                self.track.stop()
                time.sleep(0.5)

                if self._auto_abort:
                    break

                # 2. Set switches for the target track
                self.io.route_to_track(track)
                time.sleep(0.5)

                # 3. Reverse to back into the siding
                self.log(f"[AUTO] reversing into Track {track}")
                self._set_status(f"AUTO: reversing into Track {track}")
                # Wait for the track-end RFID to go empty (car coupled and moved)
                self.track.set_direction("REV")
                self.track.set_speed(50)
                ok = self._wait_track_state(track, want_car=None, timeout=30)
                if not ok and not self._auto_abort:
                    self.log(f"[AUTO] WARN: didn't see Track {track} go empty")

                # 4. Continue reverse briefly so car clears the switch zone
                time.sleep(2.5)
                self.track.stop()
                time.sleep(0.5)

                if car_at_track:
                    picked_up.append(car_at_track)

                # 5. All switches straight before continuing
                self.io.set_all_straight()
                time.sleep(0.5)

            if self._auto_abort:
                self.track.stop()
                self._set_status("AUTO: aborted")
                return

            # ── Phase 2: SAVE consist via entry RFID scan ─────────────────
            # Drive forward through entry; the cars in tow will be detected
            # in front→back order, which is reverse of pickup order
            self._set_status("AUTO: scanning consist past entry reader")
            self.car_order = []
            seen = set()
            self.track.set_direction("FWD")
            self.track.set_speed(50)
            scan_deadline = time.time() + 25
            while time.time() < scan_deadline and not self._auto_abort:
                uid = self.rfid.scan_reader(
                    train_config.ENTRY_READER_IDX, timeout_sec=0.20)
                if uid:
                    car = self.rfid.identify_car(uid)
                    if car and car not in seen:
                        seen.add(car)
                        self.car_order.append(car)
                        self.log(f"[AUTO] scanned consist position "
                                 f"{len(self.car_order)}: {car}")
                        if self.on_car_scanned:
                            self.on_car_scanned(car)
                        if len(seen) >= len(picked_up):
                            time.sleep(0.5)
                            break
                time.sleep(0.05)
            self.track.stop()
            time.sleep(0.5)

            # ── Phase 3: SORT each car to its destination ────────────────
            while self.car_order and not self._auto_abort:
                car = self.car_order[-1]  # back of train drops first
                track = self.car_destinations.get(car)
                if not track:
                    self.log(f"[AUTO] no destination for {car}, skipping")
                    self.car_order.pop()
                    continue

                self._set_status(f"AUTO: dropping {car} at Track {track}")
                self.io.route_to_track(track)
                time.sleep(0.5)

                # Reverse until that track-end RFID sees this car
                self.track.set_direction("REV")
                self.track.set_speed(50)
                ok = self._wait_track_state(track, want_car=car, timeout=30)
                # Continue back briefly to ensure car is past decoupler
                time.sleep(2.0)
                self.track.stop()
                time.sleep(0.5)

                self.io.set_all_straight()
                time.sleep(0.5)

                # Forward to entry, ready for next drop
                if self.car_order and len(self.car_order) > 1:
                    self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                           "FWD", speed=50, timeout=30)
                    self.track.stop()
                    time.sleep(0.5)

                if car in self.car_order:
                    self.car_order.remove(car)
                if self.on_drop_confirmed:
                    self.on_drop_confirmed(car, track)

            # ── Phase 4: Final return to loop ────────────────────────────
            if not self._auto_abort:
                self._set_status("AUTO: returning to loop")
                self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                       "FWD", speed=50, timeout=30)
                self.track.stop()
                self._set_status("AUTO: complete — all cars sorted")

        except Exception as e:
            self.log(f"[AUTO] error: {e}")
            self._set_status(f"AUTO: error — {e}")
        finally:
            try:
                self.track.stop()
            except Exception:
                pass
            self._auto_running = False
            self._auto_abort = False

    def show_state(self):
        self.log(f"[STATE] Consist:        {self.car_order}")
        self.log(f"[STATE] Track contents: {self.track_contents}")
        self.log(f"[STATE] Destinations:   {self.car_destinations}")

    def shutdown(self):
        self._scanning = False
        self._monitor_running = False
        self._auto_abort = True
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
