# TrainTrack.py — L298 H-bridge track power (PWM speed + direction)
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

        if pct == 0 or self.direction == "STOP":
            self._stop_pwm()
        else:
            lgpio.tx_pwm(self.chip, train_config.TRACK_ENA_PIN,
                         train_config.TRACK_PWM_FREQ, duty)
            self._pwm_active = True

    def _stop_pwm(self):
        if self.mock_mode:
            return
        try:
            lgpio.tx_pwm(self.chip, train_config.TRACK_ENA_PIN, 0, 0)
        except Exception:
            pass
        lgpio.gpio_write(self.chip, train_config.TRACK_ENA_PIN, 0)
        self._pwm_active = False

    # ── Direction ─────────────────────────────────────────────────────────────

    def set_direction(self, direction: str):
        direction = direction.upper()
        if direction not in ("FWD", "REV", "STOP"):
            self.logger(f"[TRACK] invalid direction: {direction}")
            return
        self.direction = direction

        if self.mock_mode:
            self.logger(f"[MOCK TRACK] dir={direction}")
            return

        if direction == "FWD":
            lgpio.gpio_write(self.chip, train_config.TRACK_IN1_PIN, 1)
            lgpio.gpio_write(self.chip, train_config.TRACK_IN2_PIN, 0)
        elif direction == "REV":
            lgpio.gpio_write(self.chip, train_config.TRACK_IN1_PIN, 0)
            lgpio.gpio_write(self.chip, train_config.TRACK_IN2_PIN, 1)
        else:  # STOP
            lgpio.gpio_write(self.chip, train_config.TRACK_IN1_PIN, 0)
            lgpio.gpio_write(self.chip, train_config.TRACK_IN2_PIN, 0)
            self._stop_pwm()

        # Re-apply current speed under new direction
        self.set_speed(self.speed_pct)

    def stop(self):
        self.set_direction("STOP")
        self.set_speed(0)

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
