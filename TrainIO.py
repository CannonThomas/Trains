# TrainIO.py
import time
import train_config

try:
    import lgpio
except ImportError:
    lgpio = None


class TrainIO:
    def __init__(self, logger=print):
        self.logger = logger
        self.mock_mode = train_config.MOCK_MODE or lgpio is None
        self.chip = None

        if self.mock_mode:
            if lgpio is None and not train_config.MOCK_MODE:
                self.logger("[IO] lgpio not found — running in mock mode (Mac/dev machine)")
            else:
                self.logger("[IO] MOCK_MODE enabled")
            return

        self.chip = lgpio.gpiochip_open(0)

        # Claim both coil pins for every switch as outputs, initially LOW
        for sw_name, pins in train_config.SWITCH_PINS.items():
            for direction, pin in pins.items():
                lgpio.gpio_claim_output(self.chip, pin, 0)
            self.logger(f"[IO] {sw_name} pins claimed")

        self.logger("[IO] Hardware initialized")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _pulse(self, switch_name: str, direction: str):
        """Fire one solenoid coil with a 1 ms HIGH pulse."""
        if self.mock_mode:
            self.logger(f"[MOCK IO] Pulse {switch_name} {direction}")
            return
        pin = train_config.SWITCH_PINS[switch_name][direction]
        lgpio.gpio_write(self.chip, pin, 1)
        time.sleep(train_config.SWITCH_PULSE_SEC)
        lgpio.gpio_write(self.chip, pin, 0)

    def _straight_dir(self, switch_name: str) -> str:
        siding = train_config.SWITCH_SIDING_DIR[switch_name]
        return "RIGHT" if siding == "LEFT" else "LEFT"

    # ── Public switch control ─────────────────────────────────────────────────

    def route_to_track(self, track: int):
        """
        Pulse switches for siding track 1–3.

        Track 1 = siding off S1           → pulse S1 SIDING
        Track 2 = siding off S2           → pulse S1 STRAIGHT, S2 SIDING
        Track 3 = siding off S3           → pulse S1 STRAIGHT, S2 STRAIGHT, S3 SIDING
        """
        if track not in (1, 2, 3):
            self.logger(f"[WARN] Invalid track: {track}")
            return

        switches = ["S1", "S2", "S3"]
        for i, sw in enumerate(switches):
            pos = i + 1
            if pos < track:
                self._pulse(sw, self._straight_dir(sw))
            elif pos == track:
                self._pulse(sw, train_config.SWITCH_SIDING_DIR[sw])

        self.logger(f"[IO] Routed to Track {track}")

    def set_all_straight(self):
        """Pulse every switch to STRAIGHT (main line through)."""
        for sw in train_config.SWITCH_PINS:
            self._pulse(sw, self._straight_dir(sw))
        self.logger("[IO] All switches set to main line")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        if self.mock_mode:
            self.logger("[IO] Mock cleanup")
            return
        if self.chip is not None:
            try:
                for sw_pins in train_config.SWITCH_PINS.values():
                    for pin in sw_pins.values():
                        try:
                            lgpio.gpio_free(self.chip, pin)
                        except Exception:
                            pass
                lgpio.gpiochip_close(self.chip)
            except Exception as e:
                self.logger(f"[WARN] GPIO cleanup: {e}")
            self.chip = None
        self.logger("[IO] Cleanup complete")
