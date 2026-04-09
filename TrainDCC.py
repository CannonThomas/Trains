# TrainDCC.py
import lgpio
import time
from collections import namedtuple


class TrainDCC:
    ONE_US = 58
    ZERO_US = 116

    Pulse = namedtuple("Pulse", ["group_bits", "group_mask", "pulse_delay"])

    def __init__(self, pin_a=23, pin_b=24, pin_en=18, loco_address=3, logger=print):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.pin_en = pin_en
        self.loco_address = loco_address
        self.logger = logger

        self.h = None
        self.write = None
        self.group_leader = pin_a

    def setup(self):
        if self.h is not None:
            return

        self.h = lgpio.gpiochip_open(0)

        lgpio.gpio_claim_output(self.h, self.pin_en, 0)
        lgpio.group_claim_output(self.h, [self.pin_a, self.pin_b], [0, 0])

        self.write = lgpio.gpio_write
        self.write(self.h, self.pin_en, 1)

        self.logger("[DCC] H-bridge enabled")

    def cleanup(self):
        if self.h is None:
            return

        try:
            lgpio.tx_wave(self.h, self.group_leader, [])
        except Exception:
            pass

        try:
            self.write(self.h, self.pin_en, 0)
        except Exception:
            pass

        try:
            lgpio.group_free(self.h, self.group_leader)
        except Exception:
            pass

        try:
            lgpio.gpio_free(self.h, self.pin_en)
        except Exception:
            pass

        try:
            lgpio.gpiochip_close(self.h)
        except Exception:
            pass

        self.h = None
        self.logger("[DCC] GPIO cleaned up")

    @staticmethod
    def build_dcc_packet(address, data):
        checksum = address ^ data
        return [address, data, checksum]

    @staticmethod
    def byte_to_bits(byte):
        return [(byte >> i) & 1 for i in range(7, -1, -1)]

    def build_bitstream(self, packet):
        bits = []
        bits += [1] * 14

        for byte in packet:
            bits.append(0)
            bits += self.byte_to_bits(byte)

        bits.append(1)
        return bits

    def _dcc_bit_pulses(self, us):
        return [
            self.Pulse(0b01, 0b11, us),  # A=1, B=0
            self.Pulse(0b10, 0b11, us),  # A=0, B=1
        ]

    def bitstream_to_pulses(self, bits):
        pulses = []
        for bit in bits:
            if bit == 1:
                pulses.extend(self._dcc_bit_pulses(self.ONE_US))
            else:
                pulses.extend(self._dcc_bit_pulses(self.ZERO_US))
        return pulses

    def _send_pulses(self, pulses):
        if self.h is None:
            self.setup()

        while lgpio.tx_room(self.h, self.group_leader, lgpio.TX_WAVE) <= 0:
            time.sleep(0.001)

        lgpio.tx_wave(self.h, self.group_leader, pulses)

        while lgpio.tx_busy(self.h, self.group_leader, lgpio.TX_WAVE):
            time.sleep(0.001)

    def send_bitstream(self, bits, repeat=1):
        pulses = self.bitstream_to_pulses(bits)
        for _ in range(repeat):
            self._send_pulses(pulses)

    def send_packet(self, address, data, repeat=3):
        packet = self.build_dcc_packet(address, data)
        bits = self.build_bitstream(packet)
        self.send_bitstream(bits, repeat=repeat)

    def dcc_idle(self, repeat=3):
        self.send_packet(0xFF, 0x00, repeat=repeat)
        self.logger("[DCC] idle packet sent")

    def stop(self, repeat=5):
        data = 0b00111111
        self.send_packet(self.loco_address, data, repeat=repeat)
        self.logger("[DCC] stop packet sent")

    def forward(self, speed=20, repeat=5):
        speed = max(1, min(126, speed))
        data = speed & 0x7F
        self.send_packet(self.loco_address, data, repeat=repeat)
        self.logger(f"[DCC] forward speed packet sent: {speed}")

    def reverse(self, speed=20, repeat=5):
        speed = max(1, min(126, speed))
        data = speed & 0x7F
        self.send_packet(self.loco_address, data, repeat=repeat)
        self.logger(f"[DCC] reverse speed packet sent: {speed}")

    def build_test_wave(self):
        pulses = []
        for _ in range(20):
            pulses.extend(self._dcc_bit_pulses(self.ONE_US))
        pulses.extend(self._dcc_bit_pulses(self.ZERO_US))
        return pulses

    def test_signal(self):
        if self.h is None:
            self.setup()

        self.logger("[DCC] Running tx_wave test... Ctrl+C to stop")

        try:
            while True:
                self._send_pulses(self.build_test_wave())
        except KeyboardInterrupt:
            self.logger("[DCC] Test stopped")