# TrainDCC.py
import lgpio
import time


class TrainDCC:
    """
    DCC hardware abstraction for Raspberry Pi 5 + L298N H-bridge.

    Wiring used in current project:
      GPIO18 -> L298 ENA
      GPIO23 -> L298 IN1
      GPIO24 -> L298 IN2

    This module matches the current project architecture:
      GUI -> Controller -> TrainDCC / TrainRFID / TrainIO
    """

    # NMRA-style nominal half-bit timings in microseconds
    ONE_US = 58
    ZERO_US = 116

    def __init__(self, pin_a=23, pin_b=24, pin_en=18, loco_address=3, logger=print):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.pin_en = pin_en
        self.loco_address = loco_address
        self.logger = logger

        self.h = None
        self.write = None
        self.perf = time.perf_counter

    # -------------------------------------------------
    # GPIO setup / cleanup
    # -------------------------------------------------
    def setup(self):
        self.h = lgpio.gpiochip_open(0)

        lgpio.gpio_claim_output(self.h, self.pin_a, 0)
        lgpio.gpio_claim_output(self.h, self.pin_b, 0)
        lgpio.gpio_claim_output(self.h, self.pin_en, 0)

        self.write = lgpio.gpio_write

        # enable H-bridge
        self.write(self.h, self.pin_en, 1)
        self.logger("[DCC] H-bridge enabled")

    def cleanup(self):
        if self.h is not None:
            self.write(self.h, self.pin_a, 0)
            self.write(self.h, self.pin_b, 0)
            self.write(self.h, self.pin_en, 0)
            lgpio.gpiochip_close(self.h)
            self.h = None
            self.logger("[DCC] GPIO cleaned up")

    # -------------------------------------------------
    # Low-level timing
    # -------------------------------------------------
    def _delay_us(self, us):
        end = self.perf() + (us / 1_000_000.0)
        while self.perf() < end:
            pass

    def _half_cycle(self, a_val, b_val, us):
        self.write(self.h, self.pin_a, a_val)
        self.write(self.h, self.pin_b, b_val)
        self._delay_us(us)

    def _dcc_bit(self, half_bit_us):
        # first half-cycle
        self._half_cycle(1, 0, half_bit_us)
        # second half-cycle: invert polarity
        self._half_cycle(0, 1, half_bit_us)

    def send_one(self):
        self._dcc_bit(self.ONE_US)

    def send_zero(self):
        self._dcc_bit(self.ZERO_US)

    # -------------------------------------------------
    # Packet building
    # -------------------------------------------------
    @staticmethod
    def build_dcc_packet(address, data):
        checksum = address ^ data
        return [address, data, checksum]

    @staticmethod
    def byte_to_bits(byte):
        return [(byte >> i) & 1 for i in range(7, -1, -1)]

    def build_bitstream(self, packet):
        bits = []

        # preamble: at least 14 ones
        bits += [1] * 14

        # start bit 0 before each byte
        for byte in packet:
            bits.append(0)
            bits += self.byte_to_bits(byte)

        # packet end bit
        bits.append(1)
        return bits

    # -------------------------------------------------
    # Packet sending
    # -------------------------------------------------
    def send_bitstream(self, bits, repeat=1):
        for _ in range(repeat):
            for bit in bits:
                if bit == 1:
                    self.send_one()
                else:
                    self.send_zero()

    def send_packet(self, address, data, repeat=3):
        packet = self.build_dcc_packet(address, data)
        bits = self.build_bitstream(packet)
        self.send_bitstream(bits, repeat=repeat)

    # -------------------------------------------------
    # Simple train commands
    # -------------------------------------------------
    def stop(self, repeat=5):
        """
        128-step speed packet, forward, speed 0
        Common test packet form.
        """
        data = 0b00111111
        self.send_packet(self.loco_address, data, repeat=repeat)
        self.logger("[DCC] stop packet sent")

    def forward(self, speed=1, repeat=5):
        """
        Very simple speed command placeholder.
        For now:
          speed: 1..126
        This gives the team a working interface now.
        """
        speed = max(1, min(126, speed))

        # Basic 128-step forward packet pattern
        # 0b001xxxxx style placeholder for current project testing
        # Adjust later once full command set is finalized.
        data = speed & 0x7F
        self.send_packet(self.loco_address, data, repeat=repeat)
        self.logger(f"[DCC] forward speed packet sent: {speed}")

    def test_signal(self):
        """
        Simple continuous scope test:
        lots of 1s + one 0 separator
        """
        self.logger("[DCC] Running test signal... Ctrl+C to stop")
        try:
            while True:
                for _ in range(20):
                    self.send_one()
                self.send_zero()
        except KeyboardInterrupt:
            self.logger("[DCC] Test stopped")