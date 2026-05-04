# TrainTrack.py — L298 H-bridge track power (PWM speed + direction)
import time
import train_config

try:
    import lgpio
except ImportError:
    lgpio = None


class TrainTrack:
    """
    Drives DC track power via an L298 H-bridge.

    ENA = PWM duty 0..TRACK_MAX_DUTY (caps output near 12V from 15V input)
    IN1/IN2 = direction:
        FWD: IN1=1, IN2=0
        REV: IN1=0, IN2=1
        STOP: IN1=0, IN2=0  (also duty=0)
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.mock_mode = train_config.MOCK_MODE or lgpio is None
        self.chip = None
        self.direction = "STOP"
        self.speed_pct = 0     # user-facing 0..100
        self._pwm_active = False

        if self.mock_mode:
            self.logger("[TRACK] mock mode")
            return

        self.chip = lgpio.gpiochip_open(train_config.GPIO_CHIP)
        lgpio.gpio_claim_output(self.chip, train_config.TRACK_IN1_PIN, 0)
        lgpio.gpio_claim_output(self.chip, train_config.TRACK_IN2_PIN, 0)
        lgpio.gpio_claim_output(self.chip, train_config.TRACK_ENA_PIN, 0)
        self.logger("[TRACK] L298 pins claimed (ENA/IN1/IN2)")

    # ── Speed (0..100%) ───────────────────────────────────────────────────────

    def set_speed(self, pct: int):
        pct = max(0, min(100, int(pct)))
        self.speed_pct = pct
        # Scale user 0..100 → 0..TRACK_MAX_DUTY (caps voltage at ~12V)
        duty = pct * train_config.TRACK_MAX_DUTY / 100.0

        if self.mock_mode:
            self.logger(f"[MOCK TRACK] speed={pct}% duty={duty:.1f}% dir={self.direction}")
            return

        if self.direction == "STOP":
            # Direction stopped — keep PWM at 0 but don't modify saved speed
            self._set_duty(0)
        else:
            self._set_duty(duty)

    def _set_duty(self, duty: float):
        """Drive PWM on ENA at given duty (0..100). Uses tx_pwm only — never
        falls back to gpio_write, which can leave lgpio in a state where the
        next tx_pwm call silently does nothing."""
        if self.mock_mode:
            return
        try:
            lgpio.tx_pwm(self.chip, train_config.TRACK_ENA_PIN,
                         train_config.TRACK_PWM_FREQ, duty)
            self._pwm_active = (duty > 0)
        except Exception as e:
            self.logger(f"[TRACK] tx_pwm err: {e}")

    # ── Direction ─────────────────────────────────────────────────────────────

    def set_direction(self, direction: str):
        direction = direction.upper()
        if direction not in ("FWD", "REV", "STOP"):
            self.logger(f"[TRACK] invalid direction: {direction}")
            return

        prev_speed = self.speed_pct
        prev_dir   = self.direction
        self.direction = direction

        if self.mock_mode:
            self.logger(f"[MOCK TRACK] dir={direction}")
            return

        # Cut PWM briefly so the L298 sees a clean transition.
        # Keep PWM channel alive at 0% — DON'T gpio_write the ENA pin.
        self._set_duty(0)
        lgpio.gpio_write(self.chip, train_config.TRACK_IN1_PIN, 0)
        lgpio.gpio_write(self.chip, train_config.TRACK_IN2_PIN, 0)
        time.sleep(0.05)  # dead-time so motor back-EMF settles

        if direction == "FWD":
            lgpio.gpio_write(self.chip, train_config.TRACK_IN1_PIN, 1)
            lgpio.gpio_write(self.chip, train_config.TRACK_IN2_PIN, 0)
            self.logger(f"[TRACK] FWD  IN1=1 IN2=0  speed={prev_speed}% (was {prev_dir})")
        elif direction == "REV":
            lgpio.gpio_write(self.chip, train_config.TRACK_IN1_PIN, 0)
            lgpio.gpio_write(self.chip, train_config.TRACK_IN2_PIN, 1)
            self.logger(f"[TRACK] REV  IN1=0 IN2=1  speed={prev_speed}% (was {prev_dir})")
        else:  # STOP
            self.logger(f"[TRACK] STOP IN1=0 IN2=0  (speed kept at {prev_speed}%)")
            return

        # Re-apply previous speed under new direction.
        # If user pressed FWD/REV from a stopped state with 0 speed, kick to 50%.
        if prev_speed == 0:
            prev_speed = 50
            self.logger("[TRACK] starting from 0 — kicking to 50%")
        self.set_speed(prev_speed)

    def stop(self):
        # Stop PWM and direction, but PRESERVE saved speed so REV/FWD resumes.
        self.set_direction("STOP")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        if self.mock_mode:
            return
        if self.chip is not None:
            try:
                self.stop()
                for pin in (train_config.TRACK_ENA_PIN,
                            train_config.TRACK_IN1_PIN,
                            train_config.TRACK_IN2_PIN):
                    try:
                        lgpio.gpio_free(self.chip, pin)
                    except Exception:
                        pass
                lgpio.gpiochip_close(self.chip)
            except Exception as e:
                self.logger(f"[TRACK] cleanup err: {e}")
            self.chip = None
        self.logger("[TRACK] cleanup complete")
