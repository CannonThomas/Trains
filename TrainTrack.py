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
        """Hard-stop PWM on a pin: zero duty, settle, then explicit gpio_write 0."""
        if self.mock_mode:
            return
        try:
            lgpio.tx_pwm(self.chip, pin, train_config.TRACK_PWM_FREQ, 0)
        except Exception:
            pass
        time.sleep(0.005)
        try:
            lgpio.gpio_write(self.chip, pin, 0)
        except Exception:
            pass

    def _apply(self):
        """Apply current direction + speed to the L298 pins.

        Direction safety: ENA is dropped LOW first (bridge fully disabled),
        BOTH IN pins are explicitly hard-zeroed, we wait, then ONLY the
        active direction's IN pin gets PWM, we wait again, then ENA goes HIGH.
        This sequence guarantees the L298 cannot transition through any state
        where the wrong direction's IN pin is HIGH while ENA is HIGH.
        """
        if self.mock_mode:
            self.logger(f"[MOCK TRACK] dir={self.direction} speed={self.speed_pct}%")
            return

        duty = self.speed_pct * train_config.TRACK_MAX_DUTY / 100.0
        in1 = train_config.TRACK_IN1_PIN
        in2 = train_config.TRACK_IN2_PIN
        ena = train_config.TRACK_ENA_PIN

        # 1. Disable the bridge BEFORE touching IN pins. Even if IN pins
        #    glitch, the motor sees nothing while ENA is LOW.
        lgpio.gpio_write(self.chip, ena, 0)
        time.sleep(0.005)

        # 2. Force BOTH IN pins fully off — kills any leftover PWM and
        #    hard-writes them to 0V.
        self._pwm_off(in1)
        self._pwm_off(in2)
        time.sleep(0.010)

        if self.direction == "STOP":
            return  # ENA stays LOW, both INs at 0V — motor coasting

        # 3. Start PWM on the ACTIVE IN pin only. The opposite pin is
        #    already proven LOW from step 2.
        if self.direction == "FWD":
            self._pwm(in1, duty)
            self.logger(f"[TRACK] FWD applied: PWM on IN1 (GPIO{in1}) duty={duty:.0f}%")
        elif self.direction == "REV":
            self._pwm(in2, duty)
            self.logger(f"[TRACK] REV applied: PWM on IN2 (GPIO{in2}) duty={duty:.0f}%")
        else:
            self.logger(f"[TRACK] unexpected direction: {self.direction}")
            return

        # 4. Let PWM stabilize before enabling the bridge
        time.sleep(0.010)

        # 5. Enable the bridge — only NOW does motor see voltage
        lgpio.gpio_write(self.chip, ena, 1)

    def set_speed(self, pct: int):
        """Update PWM duty ONLY on the currently active direction's pin.
        Never touches the opposite pin or ENA — eliminates any chance of
        flipping direction unintentionally."""
        self.speed_pct = max(0, min(100, int(pct)))
        if self.mock_mode:
            self.logger(f"[MOCK TRACK] speed={self.speed_pct}% dir={self.direction}")
            return

        # If we're STOPPED, the slider is a no-op until FWD/REV is pressed.
        # Refuse to drive any pin while direction is unset/STOP.
        if self.direction not in ("FWD", "REV"):
            return

        duty = self.speed_pct * train_config.TRACK_MAX_DUTY / 100.0
        active_pin = (train_config.TRACK_IN1_PIN
                      if self.direction == "FWD"
                      else train_config.TRACK_IN2_PIN)
        # Only touch the active direction's PWM pin. The opposite pin and
        # ENA were locked in by set_direction() and stay untouched.
        self._pwm(active_pin, duty)

    def set_direction(self, direction: str):
        direction = direction.upper()
        if direction not in ("FWD", "REV", "STOP"):
            self.logger(f"[TRACK] invalid direction: {direction}")
            return
        prev = self.direction
        if prev == direction:
            return

        # Reversing direction: BRAKE first (both IN HIGH, ENA HIGH) to kill
        # motor inertia, then disable bridge, then dead-time. Prevents the
        # motor from coasting backwards into the new direction at low duty.
        if not self.mock_mode and prev != "STOP" and direction != "STOP":
            in1 = train_config.TRACK_IN1_PIN
            in2 = train_config.TRACK_IN2_PIN
            ena = train_config.TRACK_ENA_PIN
            # Force both inputs HIGH at full duty → L298 brake mode
            self._pwm(in1, 100)
            self._pwm(in2, 100)
            lgpio.gpio_write(self.chip, ena, 1)
            time.sleep(0.20)  # 200ms hard brake
            # Disable bridge
            lgpio.gpio_write(self.chip, ena, 0)
            self._pwm_off(in1)
            self._pwm_off(in2)
            time.sleep(0.20)  # 200ms dead-time

        self.direction = direction
        self.logger(f"[TRACK] {prev} -> {direction} (speed={self.speed_pct}%)")
        self._apply_with_kick()

    def _apply_with_kick(self):
        """Apply direction; if speed is below 50%, kick at high duty briefly
        so the motor breaks static friction, then settle to the user's speed."""
        if self.mock_mode:
            self._apply()
            return

        target = self.speed_pct
        # If user's speed is too low to start cleanly, kick at 80% briefly
        if self.direction in ("FWD", "REV") and 0 < target < 50:
            saved = target
            self.speed_pct = 80
            self._apply()
            time.sleep(0.20)
            self.speed_pct = saved
            self.set_speed(saved)
        else:
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
