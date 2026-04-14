# test_signal.py
import lgpio
import time
from collections import namedtuple

# -----------------------
# PIN SETUP
# -----------------------
PIN_EN = 18   # L298 ENA
PIN_A  = 23   # L298 IN1
PIN_B  = 24   # L298 IN2

# DCC half-bit timing
ONE_US = 58
ZERO_US = 116

# Make wave buffer long to reduce boundary jitter
PREAMBLE_COUNT = 200
ZERO_COUNT = 20
WAVE_REPEAT = 50

Pulse = namedtuple("Pulse", ["group_bits", "group_mask", "pulse_delay"])

h = None
GROUP = PIN_A


def dcc_bit_pulses(us):
    # group order: [PIN_A, PIN_B]
    # 01 => A=1, B=0
    # 10 => A=0, B=1
    return [
        Pulse(0b01, 0b11, us),
        Pulse(0b10, 0b11, us),
    ]


def build_long_test_wave():
    pulses = []

    for _ in range(WAVE_REPEAT):
        for _ in range(PREAMBLE_COUNT):
            pulses.extend(dcc_bit_pulses(ONE_US))

        for _ in range(ZERO_COUNT):
            pulses.extend(dcc_bit_pulses(ZERO_US))

    return pulses


def main():
    global h

    h = lgpio.gpiochip_open(0)

    # Enable pin
    lgpio.gpio_claim_output(h, PIN_EN, 0)
    lgpio.gpio_write(h, PIN_EN, 1)

    # DCC complementary output group
    lgpio.group_claim_output(h, [PIN_A, PIN_B], [0, 0])

    pulses = build_long_test_wave()

    print("Running long-buffer DCC tx_wave test... Ctrl+C to stop")

    try:
        while True:
            while lgpio.tx_room(h, GROUP, lgpio.TX_WAVE) <= 0:
                time.sleep(0.001)

            lgpio.tx_wave(h, GROUP, pulses)

            while lgpio.tx_busy(h, GROUP, lgpio.TX_WAVE):
                time.sleep(0.001)

    except KeyboardInterrupt:
        print("Stopping...")

    finally:
        try:
            lgpio.tx_wave(h, GROUP, [])
        except Exception:
            pass

        try:
            lgpio.group_write(h, GROUP, 0b00, 0b11)
        except Exception:
            pass

        try:
            lgpio.gpio_write(h, PIN_EN, 0)
        except Exception:
            pass

        try:
            lgpio.group_free(h, GROUP)
        except Exception:
            pass

        try:
            lgpio.gpio_free(h, PIN_EN)
        except Exception:
            pass

        try:
            lgpio.gpiochip_close(h)
        except Exception:
            pass


if __name__ == "__main__":
    main()