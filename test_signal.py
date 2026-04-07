import gpiod
import time

# -----------------------
# GPIO SETUP
# -----------------------
PIN_A = 23   # IN1
PIN_B = 24   # IN2
PIN_EN = 18  # ENA

chip = gpiod.Chip("gpiochip4")

line_a = chip.get_line(PIN_A)
line_b = chip.get_line(PIN_B)
line_en = chip.get_line(PIN_EN)

line_a.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)
line_b.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)
line_en.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)

# Enable H-bridge
line_en.set_value(1)

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
    line_a.set_value(1)
    line_b.set_value(0)
    delay_us(us)

    # second half cycle (invert)
    line_a.set_value(0)
    line_b.set_value(1)
    delay_us(us)

def send_one():
    dcc_bit(58)   # DCC "1"

def send_zero():
    dcc_bit(100)  # DCC "0"

# -----------------------
# MAIN LOOP (TEST SIGNAL)
# -----------------------
print("Running DCC test signal...")

try:
    while True:
        # Preamble (lots of 1s)
        for _ in range(20):
            send_one()

        # One 0 to separate
        send_zero()

except KeyboardInterrupt:
    print("Stopping...")
    line_a.set_value(0)
    line_b.set_value(0)
    line_en.set_value(0)