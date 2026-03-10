# TrainIO.py

import time
from train_config import (
    MOCK_MODE,
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
)


class TrainIO:
    """
    Hardware abstraction layer for:
    - loop switch
    - cascaded sorting switches
    - crossing
    - coupler / uncoupler
    - DCC packet creation
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.switch_positions = {name: LEFT for name in SWITCH_NAMES}
        self.crossing_active = False
        self.coupler_state = "IDLE"

    def log(self, msg: str):
        self.logger(msg)

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

        # Skip spam if already in desired position
        if self.switch_positions[switch_name] == position:
            return

        self.switch_positions[switch_name] = position

        if MOCK_MODE:
            self.log(f"[MOCK] {switch_name} set to {position}")
            time.sleep(SWITCH_THROW_SEC)
            return

        # Real hardware code goes here
        self.log(f"[HW] {switch_name} set to {position}")
        time.sleep(SWITCH_THROW_SEC)

    def set_all_default(self):
        """
        Default state:
        - LOOP goes to main sorting line
        - S1/S2/S3 stay straight
        """
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
        """
        Cascaded 4-track decision tree:

        Track 1: S1 = BRANCH
        Track 2: S1 = STRAIGHT, S2 = BRANCH
        Track 3: S1 = STRAIGHT, S2 = STRAIGHT, S3 = BRANCH
        Track 4: S1 = STRAIGHT, S2 = STRAIGHT, S3 = STRAIGHT
        """
        self.log(f"[ROUTE] Setting sorting path to Track {track}")

        # Reset tree first
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

        if MOCK_MODE:
            self.log(f"[MOCK] Crossing {state}")
            return

        # Real hardware code goes here
        self.log(f"[HW] Crossing {state}")

    # -----------------------------------------
    # Coupler / uncoupler
    # -----------------------------------------
    def decouple(self):
        self.coupler_state = "DECOUPLING"

        if MOCK_MODE:
            self.log("[MOCK] Decoupler pulse fired")
            time.sleep(COUPLER_PULSE_SEC)
            self.coupler_state = "IDLE"
            return

        self.log("[HW] Decoupler pulse fired")
        time.sleep(COUPLER_PULSE_SEC)
        self.coupler_state = "IDLE"

    def couple(self):
        self.coupler_state = "COUPLING"

        if MOCK_MODE:
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

    def send_dcc_packet(self, data_bytes, label="DCC"):
        bits = self.build_dcc_packet(data_bytes)

        if MOCK_MODE:
            self.log(f"[MOCK][{label}] bytes={data_bytes}")
            return bits

        self.log(f"[HW][{label}] Sent DCC packet: {data_bytes}")
        return bits

    def dcc_loco_speed(self, address: int, speed: int, forward: bool = True):
        speed = max(0, min(speed, 28))
        direction_bit = 0x20 if forward else 0x00
        speed_byte = 0x40 | direction_bit | speed
        return self.send_dcc_packet([address, speed_byte], label="LOCO_SPEED")

    def dcc_function(self, address: int, function_group_byte: int):
        return self.send_dcc_packet([address, function_group_byte], label="LOCO_FUNC")

    def dcc_accessory(self, address: int, activate: bool = True):
        cmd = 0x01 if activate else 0x00
        return self.send_dcc_packet([address & 0xFF, cmd], label="ACCESSORY")
