# TrainIO.py

import time
from train_config import (
    MOCK_MODE,
    SWITCH_NAMES,
    LEFT,
    RIGHT,
    BRANCH,
    STRAIGHT,
    SWITCH_THROW_SEC,
    COUPLER_PULSE_SEC,
    SWITCH_GPIO,
    COUPLER_GPIO,
    CROSSING_GPIO,
)


class TrainIO:
    """
    Hardware layer.

    Switch layout:
    - S1 chooses Track 1 or continue
    - S2 chooses Track 2 or continue
    - S3 chooses Track 3 or continue
    - If all switches are STRAIGHT, car reaches Track 4

    No LOOP switch.
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.switch_positions = {name: LEFT for name in SWITCH_NAMES}
        self.crossing_active = False
        self.coupler_state = "IDLE"
        self.lines = {}

        if not MOCK_MODE:
            self._setup_gpio()

    def log(self, msg):
        self.logger(msg)

    # -------------------------------------------------
    # GPIO setup
    # -------------------------------------------------
    def _setup_gpio(self):
        import gpiod

        self.chip = gpiod.Chip("gpiochip0")

        all_output_pins = {}
        all_output_pins.update(SWITCH_GPIO)
        all_output_pins["COUPLER"] = COUPLER_GPIO
        all_output_pins["CROSSING"] = CROSSING_GPIO

        for name, pin in all_output_pins.items():
            line = self.chip.get_line(pin)
            line.request(
                consumer="train-sorter",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[0],
            )
            self.lines[name] = line

        self.log("[GPIO] Setup complete")

    def _gpio_on(self, name):
        if not MOCK_MODE:
            self.lines[name].set_value(1)

    def _gpio_off(self, name):
        if not MOCK_MODE:
            self.lines[name].set_value(0)

    # -------------------------------------------------
    # Switch control with pulse timer
    # -------------------------------------------------
    def set_switch(self, switch_name, position):
        if switch_name not in self.switch_positions:
            self.log(f"[WARN] Unknown switch: {switch_name}")
            return

        if position not in (LEFT, RIGHT):
            self.log(f"[WARN] Invalid position: {position}")
            return

        left_output = f"{switch_name}_LEFT"
        right_output = f"{switch_name}_RIGHT"

        if left_output not in SWITCH_GPIO or right_output not in SWITCH_GPIO:
            self.log(f"[WARN] Missing GPIO mapping for {switch_name}")
            return

        active_output = left_output if position == LEFT else right_output
        inactive_output = right_output if position == LEFT else left_output

        self.switch_positions[switch_name] = position

        if MOCK_MODE:
            self.log(
                f"[MOCK SWITCH] {switch_name} -> {position} "
                f"pulse {SWITCH_THROW_SEC}s"
            )
            time.sleep(SWITCH_THROW_SEC)
            return

        self._gpio_off(left_output)
        self._gpio_off(right_output)
        time.sleep(0.05)

        self._gpio_on(active_output)
        self._gpio_off(inactive_output)

        self.log(f"[GPIO SWITCH] {switch_name} -> {position} pulse ON")

        time.sleep(SWITCH_THROW_SEC)

        self._gpio_off(active_output)
        self._gpio_off(inactive_output)

        self.log(f"[GPIO SWITCH] {switch_name} -> {position} pulse OFF")

    def set_all_default(self):
        self.set_switch("S1", STRAIGHT)
        self.set_switch("S2", STRAIGHT)
        self.set_switch("S3", STRAIGHT)

    def route_to_track(self, track):
        self.log(f"[ROUTE] Setting route to Track {track}")

        if track == 1:
            self.set_switch("S1", BRANCH)
            self.set_switch("S2", STRAIGHT)
            self.set_switch("S3", STRAIGHT)

        elif track == 2:
            self.set_switch("S1", STRAIGHT)
            self.set_switch("S2", BRANCH)
            self.set_switch("S3", STRAIGHT)

        elif track == 3:
            self.set_switch("S1", STRAIGHT)
            self.set_switch("S2", STRAIGHT)
            self.set_switch("S3", BRANCH)

        elif track == 4:
            self.set_switch("S1", STRAIGHT)
            self.set_switch("S2", STRAIGHT)
            self.set_switch("S3", STRAIGHT)

        else:
            self.log(f"[WARN] Invalid track: {track}")

    # -------------------------------------------------
    # Crossing
    # -------------------------------------------------
    def set_crossing(self, active):
        if self.crossing_active == active:
            return

        self.crossing_active = active
        state = "ACTIVE" if active else "INACTIVE"

        if MOCK_MODE:
            self.log(f"[MOCK CROSSING] {state}")
            return

        if active:
            self._gpio_on("CROSSING")
        else:
            self._gpio_off("CROSSING")

        self.log(f"[GPIO CROSSING] {state}")

    # -------------------------------------------------
    # Coupler
    # -------------------------------------------------
    def decouple(self):
        self.coupler_state = "DECOUPLING"

        if MOCK_MODE:
            self.log(f"[MOCK COUPLER] Decouple pulse {COUPLER_PULSE_SEC}s")
            time.sleep(COUPLER_PULSE_SEC)
            self.coupler_state = "IDLE"
            return

        self.log(f"[GPIO COUPLER] Decouple pulse {COUPLER_PULSE_SEC}s")
        self._gpio_on("COUPLER")
        time.sleep(COUPLER_PULSE_SEC)
        self._gpio_off("COUPLER")

        self.coupler_state = "IDLE"

    # -------------------------------------------------
    # DCC placeholder
    # -------------------------------------------------
    def dcc_loco_speed(self, address, speed, forward=True):
        direction = "FORWARD" if forward else "REVERSE"
        self.log(f"[DCC PLACEHOLDER] addr={address} speed={speed} dir={direction}")

    # -------------------------------------------------
    # Cleanup
    # -------------------------------------------------
    def cleanup(self):
        if MOCK_MODE:
            self.log("[MOCK GPIO] Cleanup")
            return

        for name, line in self.lines.items():
            line.set_value(0)
            line.release()

        self.log("[GPIO] Cleanup complete")