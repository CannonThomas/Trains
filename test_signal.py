# test_signal.py
import lgpio
import time
from collections import namedtuple

# -----------------------
# GPIO SETUP
# -----------------------
PIN_A = 23   # L298 IN1
PIN_B = 24   # L298 IN2
PIN_EN = 18  # L298 ENA

# DCC nominal half-bit timings (microseconds)
ONE_US = 58
ZERO_US = 116

Pulse = namedtuple("Pulse", ["group_bits", "group_mask", "pulse_delay"])

h = None
GROUP = PIN_A  # first pin in group_claim_output


def dcc_bit_pulses(us):
    # group bits map:
    # bit0 -> PIN_A
    # bit1 -> PIN_B
    return [
        Pulse(0b01, 0b11, us),  # A=1, B=0
        Pulse(0b10, 0b11, us),  # A=0, B=1
    ]


def build_test_wave():
    pulses = []

    # preamble: 20 ones
    for _ in range(20):
        pulses.extend(dcc_bit_pulses(ONE_US))

    # separator zero
    pulses.extend(dcc_bit_pulses(ZERO_US))

    return pulses


def main():
    global h

    h = lgpio.gpiochip_open(0)

    # Enable H-bridge
    lgpio.gpio_claim_output(h, PIN_EN, 0)
    lgpio.gpio_write(h, PIN_EN, 1)

    # Claim complementary outputs as one group
    lgpio.group_claim_output(h, [PIN_A, PIN_B], [0, 0])

    print("Running DCC tx_wave test signal... Ctrl+C to stop")

    try:
        while True:
            pulses = build_test_wave()

            # wait for room in tx queue
            while lgpio.tx_room(h, GROUP, lgpio.TX_WAVE) <= 0:
                time.sleep(0.001)

            lgpio.tx_wave(h, GROUP, pulses)

            # wait until current wave finishes
            while lgpio.tx_busy(h, GROUP, lgpio.TX_WAVE):
                time.sleep(0.001)

    except KeyboardInterrupt:
        print("Stopping...")

    finally:
        try:
            lgpio.tx_wave(h, GROUP, [])  # stop any queued wave
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