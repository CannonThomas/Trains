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
                    if car and self.rfid.is_loco(car):
                        # Skip loco — it's not a car
                        last_uid = uid
                        last_time = now
                        time.sleep(0.05)
                        continue
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
        # Always-on monitor with state debouncing — flaky/sensitive readers
        # can't fire callbacks until the same reading has been confirmed
        # MONITOR_DEBOUNCE times in a row.
        MONITOR_DEBOUNCE = 3
        committed = {1: "<init>", 2: "<init>", 3: "<init>"}  # last GUI-fired state
        pending   = {1: None, 2: None, 3: None}              # candidate new state
        streak    = {1: 0, 2: 0, 3: 0}

        while self._monitor_running:
            try:
                for track in (1, 2, 3):
                    if not self._monitor_running:
                        break
                    reader_idx = train_config.TRACK_READER_IDX[track]
                    try:
                        uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.15)
                    except Exception as e:
                        self.log(f"[MON] reader {track} err: {e}")
                        uid = None
                    car = self.rfid.identify_car(uid) if uid else None
                    if car and self.rfid.is_loco(car):
                        car = None

                    # Debounce: only commit if the same reading repeats N times
                    if car == pending[track]:
                        streak[track] += 1
                    else:
                        pending[track] = car
                        streak[track] = 1

                    if (streak[track] >= MONITOR_DEBOUNCE
                            and pending[track] != committed[track]):
                        committed[track] = pending[track]
                        self.track_contents[track] = pending[track]
                        if self.on_drop_confirmed:
                            self.on_drop_confirmed(pending[track], track)

                    time.sleep(0.05)
                time.sleep(0.2)
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

    def _drive_fwd_until_tags_seen(self, expected_tags, speed=50,
                                    timeout=45.0, also_keep_going_sec=1.5):
        """Drive FWD past entry RFID, accumulating unique tags seen. Returns
        the set of tags actually detected. Stops when ALL `expected_tags` have
        been seen (or timeout). Continues another `also_keep_going_sec` past
        the last detection so the final tag has fully cleared the reader."""
        reader_idx = train_config.ENTRY_READER_IDX
        self.track.set_direction("FWD")
        self.track.set_speed(speed)
        seen = set()
        wanted = set(expected_tags)
        deadline = time.time() + timeout
        while time.time() < deadline and not self._auto_abort:
            uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.15)
            if uid:
                name = self.rfid.identify_car(uid)
                if name and name not in seen:
                    seen.add(name)
                    self.log(f"[AUTO] entry RFID saw: {name}  "
                             f"({len(seen)}/{len(wanted)})")
                    if seen >= wanted:
                        # Coast a touch so the last tag fully clears
                        end = time.time() + also_keep_going_sec
                        while time.time() < end and not self._auto_abort:
                            time.sleep(0.05)
                        self.track.stop()
                        return seen
            time.sleep(0.05)
        self.track.stop()
        return seen

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

    def _wait_track_state_with_rocking(self, track, want_car,
                                       initial_dir="REV",
                                       window_sec=8.0, max_rocks=6,
                                       rev_speed=50, fwd_speed=40,
                                       fwd_pulse_sec=1.5):
        """Wait for track-end RFID to match want_car. If it doesn't show up
        within a short window, rock the loco FWD then REV to help the coupler
        seat. Repeats up to max_rocks times."""
        reader_idx = train_config.TRACK_READER_IDX[track]
        # Initial direction
        self.track.set_direction(initial_dir)
        self.track.set_speed(rev_speed if initial_dir == "REV" else fwd_speed)

        rock_count = 0
        while rock_count <= max_rocks and not self._auto_abort:
            window_end = time.time() + window_sec
            while time.time() < window_end and not self._auto_abort:
                uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.20)
                car = self.rfid.identify_car(uid) if uid else None
                self.track_contents[track] = car
                if self.on_drop_confirmed:
                    self.on_drop_confirmed(car, track)
                if car == want_car:
                    return True
                time.sleep(0.10)

            # Window expired — try a rock
            rock_count += 1
            target_desc = "empty" if want_car is None else want_car
            self.log(f"[AUTO] coupler retry {rock_count}/{max_rocks} "
                     f"(want Track {track} = {target_desc}) — rocking")
            # Pulse FWD briefly to seat coupler
            self.track.set_direction("FWD")
            self.track.set_speed(fwd_speed)
            time.sleep(fwd_pulse_sec)
            # Then back to REV harder
            self.track.set_direction("REV")
            self.track.set_speed(rev_speed)

        self.log(f"[AUTO] giving up after {max_rocks} rocks on Track {track}")
        return False

    # ── Pickup / Drop helpers (siding has a stopper at the far end) ───────

    # Tunables
    PICKUP_REV_SECONDS = 4.0   # how long to REV into siding to reach the car
    PICKUP_FWD_TIMEOUT = 8.0   # max time to wait for car to leave RFID after FWD
    PICKUP_MAX_RETRIES = 4
    DROP_REV_TIMEOUT   = 25.0  # max time to wait for car to reach stopper RFID
    DROP_DECOUPLE_PAUSE = 1.0  # sit on stopper to let magnet decoupler engage
    DROP_FWD_VERIFY_SEC = 2.0  # FWD this long, then verify RFID still shows car

    # Debounce — number of consecutive reads required to confirm a state change.
    # Prevents flaky/sensitive RFIDs from causing false positives.
    RFID_DEBOUNCE_COUNT = 4

    def _pickup_from_track(self, track, rev_seconds=6.0,
                           rev_speed=40, fwd_speed=60):
        """Pickup logic — drives all the way to entry RFID and verifies the
        pickup there (no track-end RFID polling needed):

        1. Bulletproof STOP → REV transition (long dead-time so direction
           can never be wrong even at 60% PWM)
        2. REV for rev_seconds (push into siding to couple)
        3. Bulletproof STOP → FWD transition
        4. FWD until entry RFID detects loco AND the expected car
        5. If both seen → SUCCESS
        6. If only loco seen (no car) → loco didn't pick up the car;
           switches still set, REV again for another attempt
        """
        LOCO         = train_config.LOCO_NAME
        expected_car = self.track_contents.get(track)
        REV_SEC      = rev_seconds
        DRIVE_TO_ENTRY_TIMEOUT = 45.0
        MAX_ATTEMPTS = 6

        # Direction-change buffer — guarantees no wrong-direction glitch.
        # All pickup REV/FWD transitions go through this sequence.
        def safe_set_direction(direction, speed):
            self.track.stop()
            time.sleep(0.5)              # let any motion bleed off
            self.track.set_direction(direction)  # internal 300ms dead-time
            self.track.set_speed(speed)
            time.sleep(0.2)              # PWM settle

        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._auto_abort:
                self.track.stop()
                return False

            # ── 1. REV for allotted time ──────────────────────────────────
            self.log(f"[AUTO] === Track {track} pickup attempt "
                     f"{attempt}/{MAX_ATTEMPTS} → REV {REV_SEC}s "
                     f"@ {rev_speed}% ===")
            safe_set_direction("REV", rev_speed)
            t_end = time.time() + REV_SEC
            while time.time() < t_end and not self._auto_abort:
                time.sleep(0.05)

            if self._auto_abort:
                self.track.stop()
                return False

            # ── 2. FWD until entry RFID detects loco + expected car ──────
            self.log(f"[AUTO] Track {track} attempt {attempt} → FWD "
                     f"@ {fwd_speed}% to entry RFID")
            safe_set_direction("FWD", fwd_speed)

            seen = set()
            deadline = time.time() + DRIVE_TO_ENTRY_TIMEOUT
            while time.time() < deadline and not self._auto_abort:
                uid = self.rfid.scan_reader(
                    train_config.ENTRY_READER_IDX, timeout_sec=0.15)
                if uid:
                    name = self.rfid.identify_car(uid)
                    if name and name not in seen:
                        seen.add(name)
                        self.log(f"[AUTO]   entry detected: {name} "
                                 f"(seen so far: {seen})")
                # Pickup confirmed if loco AND expected car both seen
                # (or no expected car set, just loco)
                loco_ok = LOCO in seen
                car_ok  = (expected_car in seen) if expected_car else True
                if loco_ok and car_ok:
                    time.sleep(1.0)  # let consist clear past entry
                    self.track.stop()
                    time.sleep(0.4)
                    self.log(f"[AUTO] Track {track} pickup CONFIRMED at "
                             f"entry: {seen}")
                    return True
                time.sleep(0.05)

            # FWD timed out without seeing expected_car at entry → didn't pick up
            self.track.stop()
            time.sleep(0.5)
            if expected_car and expected_car not in seen:
                self.log(f"[AUTO] Track {track} attempt {attempt}: "
                         f"{expected_car} not seen at entry "
                         f"(saw: {seen}) — retrying REV")
            else:
                self.log(f"[AUTO] Track {track} attempt {attempt}: "
                         f"entry timeout (saw: {seen}) — retrying REV")

        self.log(f"[AUTO] Track {track}: all {MAX_ATTEMPTS} attempts failed")
        self.track.stop()
        return False

    def _drop_to_track(self, track, expected_car, rev_speed=50, fwd_speed=40):
        """Push `expected_car` (the car at the back of the train) onto the
        stopper at the end of `track`, decouple, then FWD away leaving the
        car on the RFID.

        Returns True if track-end RFID continues to show expected_car after
        the loco has pulled forward (= decouple worked).
        """
        reader_idx = train_config.TRACK_READER_IDX[track]

        # 1. REV slowly until track-end RFID detects the car (= car at stopper)
        # Debounced: require N consecutive matching reads before accepting.
        self.log(f"[AUTO] drop: REV pushing car into Track {track} stopper")
        self.track.set_direction("REV")
        self.track.set_speed(rev_speed)
        deadline = time.time() + self.DROP_REV_TIMEOUT
        arrived = False
        match_streak = 0
        while time.time() < deadline and not self._auto_abort:
            uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.20)
            car = self.rfid.identify_car(uid) if uid else None
            self.track_contents[track] = car
            if self.on_drop_confirmed:
                self.on_drop_confirmed(car, track)
            if car == expected_car:
                match_streak += 1
                if match_streak >= self.RFID_DEBOUNCE_COUNT:
                    arrived = True
                    break
            else:
                match_streak = 0
            time.sleep(0.10)
        self.track.stop()
        if not arrived:
            self.log(f"[AUTO] drop: timed out waiting for {expected_car} at "
                     f"Track {track}")

        # 2. Pause briefly while sitting on stopper to let magnetic decoupler engage
        time.sleep(self.DROP_DECOUPLE_PAUSE)

        # 3. FWD to pull loco away — car should stay on the RFID
        self.log(f"[AUTO] drop: FWD to release loco from {expected_car}")
        self.track.set_direction("FWD")
        self.track.set_speed(fwd_speed)
        time.sleep(self.DROP_FWD_VERIFY_SEC)

        # 4. Verify the car is still on the RFID (decouple succeeded)
        uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.30)
        car_still = self.rfid.identify_car(uid) if uid else None
        if car_still == expected_car:
            self.log(f"[AUTO] drop OK — {expected_car} parked on Track {track}")
            return True
        self.log(f"[AUTO] drop WARN — track {track} reads {car_still} "
                 f"(expected {expected_car})")
        return False

    def _autonomous_loop(self, pickup_order):
        FWD_SPEED = 60    # forward speed
        REV_SPEED = 40    # gentle reverse so cars don't fly off track
        SPEED = FWD_SPEED  # legacy alias for FWD-only contexts
        LOCO  = train_config.LOCO_NAME
        # Per-track REV durations on pickup
        PICKUP_REV_SEC = {1: 9.0, 2: 12.0, 3: 15.0}

        try:
            self.io.set_all_straight()
            time.sleep(0.5)

            # ── 0. Drive FWD until LOCO tag is detected at entry RFID ──
            self._set_status("AUTO ① FWD to entry — waiting for LOCO tag")
            self.log("[AUTO] driving FWD until LOCO tag at entry RFID")
            self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                   "FWD", speed=SPEED, timeout=45,
                                   expected_car=LOCO)
            self.log("[AUTO] LOCO detected at entry — anchored at loop start")
            time.sleep(0.6)
            self.track.stop()
            time.sleep(0.5)

            picked_up_cars = []  # in pickup order

            # ── 1. PICKUP each track in order ──────────────────────────────
            for i, track in enumerate(pickup_order):
                if self._auto_abort:
                    break

                car_at_track = self.track_contents.get(track)
                rev_sec = PICKUP_REV_SEC.get(track, 6.0)
                self._set_status(
                    f"AUTO ① Pickup {i+1}/3 → Track {track} "
                    f"(REV {rev_sec}s)" +
                    (f" — {car_at_track}" if car_at_track else ""))

                # Set switches for this pickup
                self.log(f"[AUTO] switches → Track {track}")
                self.io.route_to_track(track)
                time.sleep(0.6)

                # _pickup_from_track now drives all the way to entry RFID
                # and verifies the pickup by reading tags there. If the
                # expected car isn't detected at entry, it goes back and
                # retries automatically.
                ok = self._pickup_from_track(track, rev_seconds=rev_sec,
                                             rev_speed=REV_SPEED,
                                             fwd_speed=FWD_SPEED)
                if self._auto_abort:
                    break
                if ok and car_at_track and car_at_track not in picked_up_cars:
                    picked_up_cars.append(car_at_track)

                # Mainline straight after each pickup
                self.io.set_all_straight()
                time.sleep(0.5)

            if self._auto_abort:
                self.track.stop()
                self._set_status("AUTO: aborted")
                return

            # Phase 2 is implicit — by now the consist order is built from
            # the order cars were detected at entry across pickups.
            self.car_order = list(picked_up_cars)
            self.log(f"[AUTO] full consist: {self.car_order}")
            for c in self.car_order:
                if self.on_car_scanned:
                    self.on_car_scanned(c)

            # ── 2.5. PICKUP VICTORY LAP — fixed 25s FWD then transition ──
            # All 3 + loco were already confirmed at entry during pickups.
            # Just run FWD for 25 seconds (lap around the layout), then
            # cleanly transition to REV to start the drop-off phase.
            if not self._auto_abort:
                self._set_status("AUTO 🏁 Pickup victory lap — 25s FWD")
                self.log("[AUTO] starting 25s timed pickup victory lap")
                # Clean STOP → FWD transition
                self.track.stop()
                time.sleep(0.4)
                self.track.set_direction("FWD")
                self.track.set_speed(FWD_SPEED)
                t_end = time.time() + 25.0
                while time.time() < t_end and not self._auto_abort:
                    time.sleep(0.1)
                # Clean STOP before flipping to REV for drops
                self.track.stop()
                time.sleep(0.5)
                self.log("[AUTO] victory lap complete — transitioning to drops")

            # ── 3. SORT each car to its destination ───────────────────────
            while self.car_order and not self._auto_abort:
                car  = self.car_order[-1]   # back of train drops first
                dest = self.car_destinations.get(car)
                if not dest:
                    self.log(f"[AUTO] no destination for {car}, skipping")
                    self.car_order.pop()
                    continue

                self._set_status(f"AUTO ③ Drop {car} → Track {dest}")
                self.io.route_to_track(dest)
                time.sleep(0.6)

                # Drop: REV until track-end RFID shows expected car,
                # decouple, FWD away. Track must end up FULL with this car.
                self._drop_to_track(dest, expected_car=car,
                                    rev_speed=REV_SPEED, fwd_speed=FWD_SPEED)
                if self._auto_abort:
                    break

                # Verify track went FULL with the expected car (uses
                # debounced live monitor state — track_contents)
                if self.track_contents.get(dest) != car:
                    self.log(f"[AUTO] WARN: Track {dest} not showing {car}; "
                             f"contents={self.track_contents.get(dest)}")

                # Mainline straight
                self.io.set_all_straight()
                time.sleep(0.5)

                if car in self.car_order:
                    self.car_order.remove(car)
                if self.on_drop_confirmed:
                    self.on_drop_confirmed(car, dest)

                # FWD until entry RFID re-detects loco (anchor point for
                # next reverse). Use entry as the reverse-start position.
                if not self._auto_abort:
                    self._set_status("AUTO ③ Returning to entry RFID")
                    self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                           "FWD", speed=SPEED, timeout=30,
                                           expected_car=LOCO)
                    time.sleep(0.6)
                    self.track.stop()
                    time.sleep(0.5)

            if self._auto_abort:
                self.track.stop()
                self._set_status("AUTO: aborted")
                return

            # ── 4. COMPLETION — last drop done. FWD past entry, expect ONLY loco ──
            all_full = all(self.track_contents.get(t) for t in (1, 2, 3))
            self.log(f"[AUTO] sort complete. all_full={all_full}")

            self._set_status("AUTO ④ Sort done — verifying loco only at entry")
            self.track.set_direction("FWD")
            self.track.set_speed(SPEED)
            saw_loco = False
            saw_others = []
            deadline = time.time() + 30
            while time.time() < deadline and not self._auto_abort:
                uid = self.rfid.scan_reader(
                    train_config.ENTRY_READER_IDX, timeout_sec=0.15)
                if uid:
                    name = self.rfid.identify_car(uid)
                    if name == LOCO:
                        saw_loco = True
                    elif name and name not in saw_others:
                        saw_others.append(name)
                    if saw_loco:
                        time.sleep(1.0)  # let loco fully clear
                        break
                time.sleep(0.05)
            if saw_others:
                self.log(f"[AUTO] WARN: still saw cars at entry: {saw_others}")
            else:
                self.log("[AUTO] entry pass clean: loco only ✓")

            # ── 5. VICTORY LAP — keep going FWD until entry RFID hits again ──
            self._set_status("AUTO 🏁 Victory lap")
            self.log("[AUTO] running victory lap...")
            self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                   "FWD", speed=SPEED, timeout=60,
                                   expected_car=LOCO)
            time.sleep(1.0)
            self.track.stop()

            if all_full and not saw_others:
                self._set_status("AUTO ✓ Complete — all 3 sorted, victory lap done!")
            else:
                self._set_status(
                    f"AUTO finished — full={all_full}, stray={saw_others}")

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
