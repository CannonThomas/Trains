# TrainIO.py

import time
import train_config
from train_config import (
    SWITCH_NAMES,
    LEFT,
    RIGHT,
    SWITCH_THROW_SEC,
    COUPLER_PULSE_SEC,
    DCC_PREAMBLE_BITS,
    LOOP_TO_MAIN,
    LOOP_TO_VICTORY,
    BRANCH,
    STRAIGHT,
    SWITCH_PINS,
    DCC_GPIO_PIN,
    HBRIDGE_TEST_MODE,
    HBRIDGE_IN1_PIN,
    HBRIDGE_IN2_PIN,
    DCC_REPEAT_COUNT,
)

try:
    import pigpio as _pigpio
    _PIGPIO_AVAILABLE = True
except ImportError:
    _PIGPIO_AVAILABLE = False

try:
    import RPi.GPIO as _GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False


class TrainIO:
    """
    Hardware abstraction layer for:
    - loop switch
    - cascaded sorting switches
    - crossing
    - coupler / uncoupler
    - DCC packet creation
    - optional H-bridge DCC test output
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.switch_positions = {name: LEFT for name in SWITCH_NAMES}
        self.crossing_active = False
        self.coupler_state = "IDLE"
        self._pi = None
        self._gpio_ready = False

    def log(self, msg: str):
        self.logger(msg)

    # -----------------------------------------
    # Lazy hardware init
    # -----------------------------------------
    def _ensure_gpio(self):
        if self._gpio_ready or not _GPIO_AVAILABLE:
            return
        _GPIO.setmode(_GPIO.BCM)
        for pins in SWITCH_PINS.values():
            _GPIO.setup(pins["THROWN"], _GPIO.OUT, initial=_GPIO.LOW)
            _GPIO.setup(pins["CLOSED"], _GPIO.OUT, initial=_GPIO.LOW)
        self._gpio_ready = True

    def _ensure_pigpio(self):
        if self._pi is not None and self._pi.connected:
            return
        if not _PIGPIO_AVAILABLE:
            return
        self._pi = _pigpio.pi()
        if self._pi.connected:
            self._pi.set_mode(DCC_GPIO_PIN, _pigpio.OUTPUT)
            self._pi.write(DCC_GPIO_PIN, 0)
            self._pi.set_mode(HBRIDGE_IN1_PIN, _pigpio.OUTPUT)
            self._pi.set_mode(HBRIDGE_IN2_PIN, _pigpio.OUTPUT)
            self._pi.write(HBRIDGE_IN1_PIN, 0)
            self._pi.write(HBRIDGE_IN2_PIN, 0)
        else:
            self.log("[WARN] pigpio daemon not reachable — DCC disabled")
            self._pi = None

    # -----------------------------------------
    # Switch control
    # -----------------------------------------
    def set_switch(self, switch_name: str, position: str):
        if switch_name not in self.switch_positions:
            self.log(f"[WARN] Unknown switch: {switch_name}")
            return

        if position not in (LEFT, RIGHT):
            self.log(f"[WARN] Invalid position for {switch_name}: {position}")
            return

        if self.switch_positions[switch_name] == position:
            return

        self.switch_positions[switch_name] = position

        if train_config.MOCK_MODE:
            self.log(f"[MOCK] {switch_name} set to {position}")
            time.sleep(SWITCH_THROW_SEC)
            return

        self.log(f"[HW] {switch_name} set to {position}")
        self._ensure_gpio()
        if _GPIO_AVAILABLE and self._gpio_ready:
            pin = SWITCH_PINS[switch_name]["THROWN" if position == RIGHT else "CLOSED"]
            _GPIO.output(pin, _GPIO.HIGH)
            time.sleep(SWITCH_THROW_SEC)
            _GPIO.output(pin, _GPIO.LOW)
        else:
            time.sleep(SWITCH_THROW_SEC)

    def set_all_default(self):
        self.set_switch("LOOP", LOOP_TO_MAIN)
        self.set_switch("S1", STRAIGHT)
        self.set_switch("S2", STRAIGHT)
        self.set_switch("S3", STRAIGHT)

    def route_to_main_from_loop(self):
        self.log("[ROUTE] Victory Lap -> Main sorting line")
        self.set_switch("LOOP", LOOP_TO_MAIN)

    def route_to_victory_lap(self):
        self.log("[ROUTE] Main sorting line -> Victory Lap")
        self.set_switch("LOOP", LOOP_TO_VICTORY)

    def route_to_track(self, track: int):
        self.log(f"[ROUTE] Setting sorting path to Track {track}")

        self.set_switch("LOOP", LOOP_TO_MAIN)
        self.set_switch("S1", STRAIGHT)
        self.set_switch("S2", STRAIGHT)
        self.set_switch("S3", STRAIGHT)

        if track == 1:
            self.set_switch("S1", BRANCH)
        elif track == 2:
            self.set_switch("S2", BRANCH)
        elif track == 3:
            self.set_switch("S3", BRANCH)
        elif track == 4:
            pass
        else:
            self.log(f"[WARN] Invalid track number: {track}")

    # -----------------------------------------
    # Crossing control
    # -----------------------------------------
    def set_crossing(self, active: bool):
        if self.crossing_active == active:
            return

        self.crossing_active = active
        state = "ACTIVE" if active else "INACTIVE"

        if train_config.MOCK_MODE:
            self.log(f"[MOCK] Crossing {state}")
            return

        self.log(f"[HW] Crossing {state}")

    # -----------------------------------------
    # Coupler / uncoupler
    # -----------------------------------------
    def decouple(self):
        self.coupler_state = "DECOUPLING"

        if train_config.MOCK_MODE:
            self.log("[MOCK] Decoupler pulse fired")
            time.sleep(COUPLER_PULSE_SEC)
            self.coupler_state = "IDLE"
            return

        self.log("[HW] Decoupler pulse fired")
        time.sleep(COUPLER_PULSE_SEC)
        self.coupler_state = "IDLE"

    def couple(self):
        self.coupler_state = "COUPLING"

        if train_config.MOCK_MODE:
            self.log("[MOCK] Coupling sequence")
            time.sleep(COUPLER_PULSE_SEC)
            self.coupler_state = "IDLE"
            return

        self.log("[HW] Coupling sequence")
        time.sleep(COUPLER_PULSE_SEC)
        self.coupler_state = "IDLE"

    # -----------------------------------------
    # DCC helpers
    # -----------------------------------------
    def xor_checksum(self, data_bytes):
        checksum = 0
        for value in data_bytes:
            checksum ^= value
        return checksum

    def build_dcc_packet(self, data_bytes):
        checksum = self.xor_checksum(data_bytes)
        full_bytes = list(data_bytes) + [checksum]

        bits = []
        bits.extend([1] * DCC_PREAMBLE_BITS)
        bits.append(0)

        for index, byte in enumerate(full_bytes):
            for bit_index in range(7, -1, -1):
                bits.append((byte >> bit_index) & 1)

            if index == len(full_bytes) - 1:
                bits.append(1)
            else:
                bits.append(0)

        return bits

    def _send_dcc_hbridge_packet(self, bits, label="DCC"):
        """
        Send DCC by driving a 2-input H-bridge with complementary outputs.

        Half-cycle mapping:
        - first half:  IN1=1, IN2=0
        - second half: IN1=0, IN2=1

        DCC timing:
        - bit 1 = 58us + 58us
        - bit 0 = 116us + 116us
        """
        self._ensure_pigpio()
        if not (_PIGPIO_AVAILABLE and self._pi is not None and self._pi.connected):
            self.log("[WARN] pigpio unavailable, H-bridge DCC not sent")
            return False

        mask_in1 = 1 << HBRIDGE_IN1_PIN
        mask_in2 = 1 << HBRIDGE_IN2_PIN

        pulses = []
        for _ in range(DCC_REPEAT_COUNT):
            for bit in bits:
                half = 58 if bit == 1 else 116
                pulses.append(_pigpio.pulse(mask_in1, mask_in2, half))
                pulses.append(_pigpio.pulse(mask_in2, mask_in1, half))

        self._pi.wave_clear()
        self._pi.wave_add_generic(pulses)
        wid = self._pi.wave_create()
        if wid < 0:
            self.log("[WARN] Failed to create pigpio wave")
            return False

        self._pi.wave_send_once(wid)
        while self._pi.wave_tx_busy():
            time.sleep(0.001)

        self._pi.wave_delete(wid)
        self._pi.write(HBRIDGE_IN1_PIN, 0)
        self._pi.write(HBRIDGE_IN2_PIN, 0)

        self.log(f"[HW][{label}] Sent H-bridge DCC packet")
        return True

    def _send_dcc_single_pin_packet(self, bits, label="DCC"):
        """
        Old single-pin fallback. Useful only if your hardware later expects one DCC input.
        """
        self._ensure_pigpio()
        if not (_PIGPIO_AVAILABLE and self._pi is not None and self._pi.connected):
            self.log("[WARN] pigpio unavailable, single-pin DCC not sent")
            return False

        pin_mask = 1 << DCC_GPIO_PIN
        pulses = []
        for _ in range(DCC_REPEAT_COUNT):
            for bit in bits:
                half = 58 if bit == 1 else 116
                pulses.append(_pigpio.pulse(pin_mask, 0, half))
                pulses.append(_pigpio.pulse(0, pin_mask, half))

        self._pi.wave_clear()
        self._pi.wave_add_generic(pulses)
        wid = self._pi.wave_create()
        if wid < 0:
            self.log("[WARN] Failed to create pigpio wave")
            return False

        self._pi.wave_send_once(wid)
        while self._pi.wave_tx_busy():
            time.sleep(0.001)

        self._pi.wave_delete(wid)
        self._pi.write(DCC_GPIO_PIN, 0)

        self.log(f"[HW][{label}] Sent single-pin DCC packet")
        return True

    def send_dcc_packet(self, data_bytes, label="DCC"):
        bits = self.build_dcc_packet(data_bytes)

        if train_config.MOCK_MODE:
            self.log(f"[MOCK][{label}] bytes={data_bytes}, bits={bits}")
            return bits

        if HBRIDGE_TEST_MODE:
            self._send_dcc_hbridge_packet(bits, label=label)
        else:
            self._send_dcc_single_pin_packet(bits, label=label)

        return bits

    def dcc_loco_speed(self, address: int, speed: int, forward: bool = True):
        speed = max(0, min(speed, 28))
        direction_bit = 0x20 if forward else 0x00
        speed_byte = 0x40 | direction_bit | speed
        return self.send_dcc_packet([address, speed_byte], label="LOCO_SPEED")

    def dcc_idle(self):
        # Common simple idle packet
        return self.send_dcc_packet([0xFF, 0x00], label="IDLE")

    def dcc_function(self, address: int, function_group_byte: int):
        return self.send_dcc_packet([address, function_group_byte], label="LOCO_FUNC")

    def dcc_accessory(self, address: int, activate: bool = True):
        cmd = 0x01 if activate else 0x00
        return self.send_dcc_packet([address & 0xFF, cmd], label="ACCESSORY")