import lgpio
import time

# -----------------------
# GPIO SETUP
# -----------------------
PIN_A = 23   # IN1
PIN_B = 24   # IN2
PIN_EN = 18  # ENA

h = lgpio.gpiochip_open(0)

lgpio.gpio_claim_output(h, PIN_A, 0)
lgpio.gpio_claim_output(h, PIN_B, 0)
lgpio.gpio_claim_output(h, PIN_EN, 0)

# Enable H-bridge
lgpio.gpio_write(h, PIN_EN, 1)

# -----------------------
# MICROSECOND DELAY
# -----------------------
def delay_us(us):
    start = time.perf_counter()
    end = start + us / 1_000_000.0
    while time.perf_counter() < end:
        pass

# -----------------------
# DCC BIT GENERATION
# -----------------------
def dcc_bit(us):
    # first half cycle
    lgpio.gpio_write(h, PIN_A, 1)
    lgpio.gpio_write(h, PIN_B, 0)
    delay_us(us)

    # second half cycle (invert)
    lgpio.gpio_write(h, PIN_A, 0)
    lgpio.gpio_write(h, PIN_B, 1)
    delay_us(us)

def send_one():
    dcc_bit(58)   # DCC "1" half-bit

def send_zero():
    dcc_bit(100)  # your current test "0" half-bit

# -----------------------
# MAIN LOOP (TEST SIGNAL)
# -----------------------
print("Running DCC test signal... Press Ctrl+C to stop.")

try:
    while True:
        # Preamble
        for _ in range(20):
            send_one()

        # Separator
        send_zero()

except KeyboardInterrupt:
    print("Stopping...")

finally:
    lgpio.gpio_write(h, PIN_A, 0)
    lgpio.gpio_write(h, PIN_B, 0)
    lgpio.gpio_write(h, PIN_EN, 0)
    lgpio.gpiochip_close(h)