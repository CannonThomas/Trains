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

    def _pickup_from_track(self, track, rev_speed=50, fwd_speed=50):
        """Couple to a stationary car at the end of `track` by rocking the
        loco REV/FWD up to MAX_ROCKS times.

        During each FWD phase we poll the track-end RFID. If it goes empty
        (debounced) we KEEP the loco moving FWD — that confirms the car was
        pulled away from the stopper. Then the caller drives the rest of
        the way to the entry RFID without an extra direction change.

        REV phases just run for the full timer (no early-exit), since on
        the way IN there's nothing useful to detect.
        """
        REV_PHASE_SEC = 4.0
        FWD_PHASE_SEC = 3.0
        STOP_BETWEEN  = 0.7
        MAX_ROCKS     = 6
        DEBOUNCE      = self.RFID_DEBOUNCE_COUNT
        reader_idx    = train_config.TRACK_READER_IDX[track]

        def run_rev(duration):
            """Set REV, run for `duration`, then stop with dead-time."""
            if self._auto_abort:
                return
            self.log(f"[AUTO] pickup → REV for {duration}s @ {rev_speed}%")
            self.track.set_direction("REV")
            self.track.set_speed(rev_speed)
            t_end = time.time() + duration
            while time.time() < t_end and not self._auto_abort:
                time.sleep(0.05)
            self.track.stop()
            t_end = time.time() + STOP_BETWEEN
            while time.time() < t_end and not self._auto_abort:
                time.sleep(0.05)

        def run_fwd_watch(duration):
            """Set FWD, run for `duration`, polling track-end RFID. Returns
            True if RFID confirmed empty (car extracted) — leaves loco
            running FWD so the caller can continue to entry RFID."""
            if self._auto_abort:
                return False
            self.log(f"[AUTO] pickup → FWD for {duration}s @ {fwd_speed}% "
                     f"(watching Track {track} RFID)")
            self.track.set_direction("FWD")
            self.track.set_speed(fwd_speed)
            t_end = time.time() + duration
            empty_streak = 0
            while time.time() < t_end and not self._auto_abort:
                uid = self.rfid.scan_reader(reader_idx, timeout_sec=0.15)
                car = self.rfid.identify_car(uid) if uid else None
                self.track_contents[track] = car
                if self.on_drop_confirmed:
                    self.on_drop_confirmed(car, track)
                if car is None:
                    empty_streak += 1
                    if empty_streak >= DEBOUNCE:
                        # Car confirmed pulled away — keep going FWD
                        self.log(f"[AUTO] Track {track} RFID empty (debounced)"
                                 f" — pickup confirmed, staying FWD")
                        return True
                else:
                    empty_streak = 0
                time.sleep(0.05)
            # Time out — full stop + dead-time before next REV
            self.track.stop()
            t_end = time.time() + STOP_BETWEEN
            while time.time() < t_end and not self._auto_abort:
                time.sleep(0.05)
            return False

        for rock in range(1, MAX_ROCKS + 1):
            if self._auto_abort:
                self.track.stop()
                return False
            self.log(f"[AUTO] === Track {track} rock {rock}/{MAX_ROCKS} ===")
            run_rev(REV_PHASE_SEC)
            if run_fwd_watch(FWD_PHASE_SEC):
                # Car gone — loco still running FWD, exit early
                return True

        self.log(f"[AUTO] {MAX_ROCKS} rocks complete on Track {track}; "
                 f"continuing FWD to confirm at entry RFID")
        # Make sure loco is moving FWD for the entry-RFID confirmation step
        self.track.set_direction("FWD")
        self.track.set_speed(fwd_speed)
        return True

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
        SPEED = 50
        try:
            self.io.set_all_straight()
            time.sleep(0.5)

            # ── Phase 1: PICKUP — loco starts in loop, reverses to grab cars ──
            # Each pickup ends by driving FWD back to the entry RFID so the
            # entry reader can confirm the just-picked-up car (proving it's
            # coupled and being pulled) and re-anchor position for the next
            # reverse move.
            #
            # The very first pickup also begins from the entry RFID — loco
            # drives FWD until entry sees it, then stops at the loop start,
            # then reverses with switches set.

            # 0. ALWAYS start the routine by driving FWD until the entry RFID
            #    detects something (loco's own tag or a car). This anchors the
            #    loco at a known position before the first reverse.
            self._set_status("AUTO ① Driving FWD to entry RFID before first pickup")
            self.log("[AUTO] starting FWD until entry RFID detection")
            found = self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                           "FWD", speed=SPEED, timeout=30)
            if found:
                self.log("[AUTO] entry RFID hit — loco at loop start")
            else:
                self.log("[AUTO] WARN: entry RFID never triggered; "
                         "starting pickup anyway")
            time.sleep(0.8)
            self.track.stop()
            time.sleep(0.5)

            for i, track in enumerate(pickup_order):
                if self._auto_abort:
                    break
                car_at_track = self.track_contents.get(track)
                self._set_status(
                    f"AUTO ① Pickup {i+1}/{len(pickup_order)} → Track {track}"
                    + (f" ({car_at_track})" if car_at_track else ""))

                # Set switches BEFORE reversing
                self.log(f"[AUTO] switches → Track {track}")
                self.io.route_to_track(track)
                time.sleep(0.6)

                # Pickup: REV into siding to couple, then FWD to pull car out
                ok = self._pickup_from_track(track, rev_speed=SPEED)
                if not ok and not self._auto_abort:
                    self.log(f"[AUTO] WARN: Track {track} pickup failed")

                # Mainline straight, then run FWD to entry RFID. The entry
                # reader confirms the just-picked-up car and serves as the
                # start position for the next reverse pickup.
                self.io.set_all_straight()
                time.sleep(0.5)

                if not self._auto_abort:
                    self._set_status(
                        f"AUTO ① Confirming {car_at_track or 'pickup'} "
                        f"at entry RFID")
                    confirm_target = car_at_track  # exact car if known
                    confirmed = self._drive_until_rfid(
                        train_config.ENTRY_READER_IDX, "FWD", speed=SPEED,
                        timeout=30, expected_car=confirm_target)
                    if confirmed:
                        self.log(f"[AUTO] entry RFID confirmed pickup of "
                                 f"{confirm_target or 'a car'}")
                    else:
                        self.log(f"[AUTO] WARN: entry RFID didn't confirm "
                                 f"{confirm_target} within timeout")
                    # Coast slightly past so loco is just past entry, ready
                    # to reverse with switches set.
                    time.sleep(0.8)
                    self.track.stop()
                    time.sleep(0.4)

            if self._auto_abort:
                self.track.stop()
                self._set_status("AUTO: aborted")
                return

            empties = [t for t in pickup_order if not self.track_contents.get(t)]
            self.log(f"[AUTO] picked-up tracks now empty: {empties}")

            # ── Phase 2: Confirm full consist via entry RFID ───────────────
            # The cars were each confirmed at entry during their pickup pass,
            # but we re-scan one more time so car_order reflects the actual
            # order they pass the entry reader (front→back of train).
            self._set_status("AUTO ② Confirming full consist at entry RFID")
            self.car_order = []
            seen = set()
            target = len(pickup_order)
            self.track.set_direction("FWD")
            self.track.set_speed(SPEED)
            scan_deadline = time.time() + 30
            while (len(seen) < target and time.time() < scan_deadline
                   and not self._auto_abort):
                uid = self.rfid.scan_reader(
                    train_config.ENTRY_READER_IDX, timeout_sec=0.20)
                if uid:
                    car = self.rfid.identify_car(uid)
                    # Skip the locomotive itself — it's not part of the consist
                    if car and not self.rfid.is_loco(car) and car not in seen:
                        seen.add(car)
                        self.car_order.append(car)
                        self.log(f"[AUTO] consist {len(self.car_order)}: {car}")
                        if self.on_car_scanned:
                            self.on_car_scanned(car)
                time.sleep(0.05)
            time.sleep(1.0)  # let last car clear past entry
            self.track.stop()
            time.sleep(0.5)
            self.log(f"[AUTO] full consist (front→back): {self.car_order}")

            # ── Phase 3: SORT — reverse, drop each car at destination ─────
            while self.car_order and not self._auto_abort:
                car = self.car_order[-1]   # back of train drops first
                dest = self.car_destinations.get(car)
                if not dest:
                    self.log(f"[AUTO] no destination for {car}, skipping")
                    self.car_order.pop()
                    continue

                self._set_status(f"AUTO ③ Drop {car} → Track {dest}")
                self.io.route_to_track(dest)
                time.sleep(0.6)

                # Drop: REV pushes car against stopper, decoupler engages,
                # then FWD pulls loco away leaving the car on the RFID.
                self._drop_to_track(dest, expected_car=car, rev_speed=SPEED)

                self.io.set_all_straight()
                time.sleep(0.5)

                # Drop car from consist
                if car in self.car_order:
                    self.car_order.remove(car)
                if self.on_drop_confirmed:
                    self.on_drop_confirmed(car, dest)

                # If more cars remain, forward to entry RFID to re-scan / reposition
                if self.car_order and not self._auto_abort:
                    self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                           "FWD", speed=SPEED, timeout=30)
                    time.sleep(1.0)
                    self.track.stop()
                    time.sleep(0.4)

            if self._auto_abort:
                self.track.stop()
                self._set_status("AUTO: aborted")
                return

            # ── Phase 4: DONE — last drop confirmed, loco runs FWD to finish ──
            all_full = all(self.track_contents.get(t) for t in (1, 2, 3))
            self.log(f"[AUTO] all_full={all_full}, contents={self.track_contents}")
            self._set_status("AUTO ④ Done — running forward in loop")
            self.track.set_direction("FWD")
            self.track.set_speed(SPEED)
            # Drive forward until entry RFID hit once, then stop (loco parked in loop)
            self._drive_until_rfid(train_config.ENTRY_READER_IDX,
                                   "FWD", speed=SPEED, timeout=30)
            time.sleep(1.0)
            self.track.stop()
            if all_full:
                self._set_status("AUTO ✓ Complete — all 3 cars sorted!")
            else:
                self._set_status(
                    f"AUTO finished — track_contents={self.track_contents}")

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
