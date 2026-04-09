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
        self.perf = time.perf_counter
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
        except:
            pass

        self.write(self.h, self.pin_en, 0)
        lgpio.group_free(self.h, self.group_leader)
        lgpio.gpio_free(self.h, self.pin_en)
        lgpio.gpiochip_close(self.h)
        self.h = None

    # -----------------------------
    # OLD BIT (still used for packets)
    # -----------------------------
    def _delay_us(self, us):
        end = self.perf() + (us / 1_000_000.0)
        while self.perf() < end:
            pass

    def _half_cycle(self, a, b, us):
        self.write(self.h, self.pin_a, a)
        self.write(self.h, self.pin_b, b)
        self._delay_us(us)

    def _dcc_bit(self, us):
        self._half_cycle(1, 0, us)
        self._half_cycle(0, 1, us)

    def send_one(self):
        self._dcc_bit(self.ONE_US)

    def send_zero(self):
        self._dcc_bit(self.ZERO_US)

    # -----------------------------
    # TX_WAVE TEST SIGNAL (NEW)
    # -----------------------------
    def _dcc_bit_pulses(self, us):
        return [
            self.Pulse(0b01, 0b11, us),
            self.Pulse(0b10, 0b11, us),
        ]

    def build_test_wave(self):
        pulses = []

        for _ in range(20):
            pulses.extend(self._dcc_bit_pulses(self.ONE_US))

        pulses.extend(self._dcc_bit_pulses(self.ZERO_US))
        return pulses

    def test_signal(self):
        self.logger("[DCC] Running tx_wave test...")

        while True:
            pulses = self.build_test_wave()

            while lgpio.tx_room(self.h, self.group_leader, lgpio.TX_WAVE) <= 0:
                time.sleep(0.001)

            lgpio.tx_wave(self.h, self.group_leader, pulses)

            while lgpio.tx_busy(self.h, self.group_leader, lgpio.TX_WAVE):
                time.sleep(0.001)