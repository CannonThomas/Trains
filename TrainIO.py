# TrainIO.py
import time
import train_config
from TrainDCC import TrainDCC

try:
    from TrainMock import TrainMock
except ImportError:
    TrainMock = None

try:
    import lgpio
except ImportError:
    lgpio = None


class TrainIO:
    def __init__(self, logger=print):
        self.logger = logger
        self.mock_mode = train_config.MOCK_MODE
        self.chip = None
        self.dcc = None

        if self.mock_mode:
            self.mock = TrainMock(logger=self.logger) if TrainMock else None
            self.logger("[IO] MOCK_MODE enabled")
            return

        self.mock = None

        if lgpio is None:
            raise RuntimeError("lgpio is required for real hardware mode")

        self.chip = lgpio.gpiochip_open(0)

        # Claim both coil pins for every switch as outputs, initially LOW
        for sw_name, pins in train_config.SWITCH_PINS.items():
            for direction, pin in pins.items():
                lgpio.gpio_claim_output(self.chip, pin, 0)

        dcc_p = train_config.DCC_PINS
        self.dcc = TrainDCC(
            pin_a=dcc_p["IN1"],
            pin_b=dcc_p["IN2"],
            pin_en=dcc_p["ENA"],
            loco_address=train_config.LOCO_ADDRESS,
            logger=self.logger,
        )
        self.dcc.setup()
        self.logger("[IO] Real hardware initialized")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _pulse_switch(self, switch_name: str, direction: str):
        """Fire one solenoid coil with a 1 ms HIGH pulse."""
        if self.mock_mode:
            self.logger(f"[MOCK IO] Pulse {switch_name} {direction}")
            return
        pin = train_config.SWITCH_PINS[switch_name][direction]
        lgpio.gpio_write(self.chip, pin, 1)
        time.sleep(train_config.SWITCH_PULSE_SEC)
        lgpio.gpio_write(self.chip, pin, 0)

    def _straight_dir(self, switch_name: str) -> str:
        """Return the direction that routes the train straight through (not to siding)."""
        siding = train_config.SWITCH_SIDING_DIR[switch_name]
        return "RIGHT" if siding == "LEFT" else "LEFT"

    # ── DCC helpers ───────────────────────────────────────────────────────────

    def dcc_idle(self):
        if self.mock_mode:
            self.logger("[MOCK DCC] idle")
            return
        self.dcc.dcc_idle()

    def dcc_loco_speed(self, address, speed, forward=True):
        if self.mock_mode:
            self.logger(f"[MOCK DCC] addr={address} speed={speed} dir={'fwd' if forward else 'rev'}")
            return
        self.dcc.set_address(address)
        if speed <= 0:
            self.dcc.stop()
        elif forward:
            self.dcc.forward(speed)
        else:
            self.dcc.reverse(speed)

    def dcc_power_off(self):
        if self.mock_mode:
            self.logger("[MOCK DCC] power off")
            return
        self.dcc.power_off()

    # ── Routing / turnouts ────────────────────────────────────────────────────

    def route_to_track(self, track: int):
        """
        Set switches for a siding track (1–3) using 1 ms impulses.
        Switches before the target are pulsed STRAIGHT; the target switch
        is pulsed SIDING.  Switches after the target are left alone.

        Track 1 = siding off S1
        Track 2 = siding off S2  (train passes S1 straight first)
        Track 3 = siding off S3  (train passes S1 and S2 straight first)
        """
        if track < 1 or track > 3:
            self.logger(f"[WARN] Invalid track: {track}")
            return

        switch_order = ["S1", "S2", "S3"]
        for i, sw in enumerate(switch_order):
            position = i + 1          # switch number matches track number at that position
            if position < track:
                self._pulse_switch(sw, self._straight_dir(sw))
            elif position == track:
                self._pulse_switch(sw, train_config.SWITCH_SIDING_DIR[sw])
            # switches after the target don't need to be touched

        self.logger(f"[IO] Routed to Track {track}")

    def set_all_default(self):
        """Pulse every switch to STRAIGHT (main line through)."""
        for sw in train_config.SWITCH_PINS:
            self._pulse_switch(sw, self._straight_dir(sw))
        self.logger("[IO] All switches set to main line")

    def set_crossing(self, enabled):
        # Placeholder — wire a crossing signal here if your layout has one
        self.logger(f"[IO] Crossing {'ON' if enabled else 'OFF'}")

    def decouple(self, pulse_sec=0.25):
        # Add a DECOUPLE pin to SWITCH_PINS or a separate config entry if needed
        self.logger("[IO] Decouple called (no pin configured — add one in train_config if required)")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        if self.mock_mode:
            self.logger("[IO] Mock cleanup")
            return

        try:
            self.set_all_default()
        except Exception:
            pass

        try:
            if self.dcc:
                self.dcc.power_off()
                self.dcc.cleanup()
        except Exception as e:
            self.logger(f"[WARN] DCC cleanup: {e}")

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
