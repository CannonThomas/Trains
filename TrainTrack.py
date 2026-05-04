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

    # ── Sign-magnitude PWM ──────────────────────────────────────────────────
    # ENA tied HIGH. Direction = which IN pin gets PWM, the other LOW.
    #   FWD: IN1=PWM, IN2=0
    #   REV: IN1=0,   IN2=PWM
    #   STOP: ENA=0,  IN1=0, IN2=0

    def _pwm(self, pin: int, duty: float):
        if self.mock_mode:
            return
        try:
            lgpio.tx_pwm(self.chip, pin, train_config.TRACK_PWM_FREQ, duty)
        except Exception as e:
            self.logger(f"[TRACK] tx_pwm({pin}) err: {e}")

    def _pwm_off(self, pin: int):
        if self.mock_mode:
            return
        try:
            lgpio.tx_pwm(self.chip, pin, train_config.TRACK_PWM_FREQ, 0)
        except Exception:
            pass
        try:
            lgpio.gpio_write(self.chip, pin, 0)
        except Exception:
            pass

    def _apply(self):
        """Apply current direction + speed to the L298 pins."""
        if self.mock_mode:
            self.logger(f"[MOCK TRACK] dir={self.direction} speed={self.speed_pct}%")
            return

        duty = self.speed_pct * train_config.TRACK_MAX_DUTY / 100.0
        in1 = train_config.TRACK_IN1_PIN
        in2 = train_config.TRACK_IN2_PIN
        ena = train_config.TRACK_ENA_PIN

        # Always disable the bridge first so we can configure IN pins cleanly
        # without any chance of a brief opposite pulse.
        lgpio.gpio_write(self.chip, ena, 0)

        if self.direction == "STOP":
            self._pwm_off(in1)
            self._pwm_off(in2)
            return

        # Hard-zero the OPPOSITE pin first, settle, then start PWM on the
        # active pin, settle, then enable the bridge.
        if self.direction == "FWD":
            self._pwm_off(in2)
            time.sleep(0.005)
            self._pwm(in1, duty)
        else:  # REV
            self._pwm_off(in1)
            time.sleep(0.005)
            self._pwm(in2, duty)
        time.sleep(0.010)               # let PWM stabilize
        lgpio.gpio_write(self.chip, ena, 1)

    def set_speed(self, pct: int):
        """Update PWM duty ONLY — never touches direction pins or ENA.
        This prevents speed changes from causing transient direction glitches."""
        self.speed_pct = max(0, min(100, int(pct)))
        if self.mock_mode:
            self.logger(f"[MOCK TRACK] speed={self.speed_pct}% dir={self.direction}")
            return

        duty = self.speed_pct * train_config.TRACK_MAX_DUTY / 100.0
        in1 = train_config.TRACK_IN1_PIN
        in2 = train_config.TRACK_IN2_PIN

        # Only adjust the active direction's PWM pin. Leave the other pin and
        # ENA exactly where set_direction last put them.
        if self.direction == "FWD":
            self._pwm(in1, duty)
        elif self.direction == "REV":
            self._pwm(in2, duty)
        # STOP: do nothing — slider has no effect until a direction is chosen

    def set_direction(self, direction: str):
        direction = direction.upper()
        if direction not in ("FWD", "REV", "STOP"):
            self.logger(f"[TRACK] invalid direction: {direction}")
            return
        prev = self.direction
        if prev == direction:
            return  # no-op, prevents redundant pulses

        # Always pass through a STOP state with dead-time before changing
        # direction. Prevents motor reversal glitches and L298 confusion.
        if not self.mock_mode and prev != "STOP" and direction != "STOP":
            self._pwm_off(train_config.TRACK_IN1_PIN)
            self._pwm_off(train_config.TRACK_IN2_PIN)
            lgpio.gpio_write(self.chip, train_config.TRACK_ENA_PIN, 0)
            time.sleep(0.30)  # 300ms dead-time

        self.direction = direction
        self.logger(f"[TRACK] {prev} -> {direction} (speed={self.speed_pct}%)")
        self._apply()

    def stop(self):
        # Cuts power but PRESERVES speed_pct so FWD/REV resumes at same speed.
        self.direction = "STOP"
        self.logger(f"[TRACK] STOP (speed kept at {self.speed_pct}%)")
        self._apply()

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
