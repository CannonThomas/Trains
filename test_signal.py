import gpiod
import time

chip = gpiod.Chip('gpiochip4')  # Pi 5 uses gpiochip4

PIN_A = 23
PIN_B = 24

line_a = chip.get_line(PIN_A)
line_b = chip.get_line(PIN_B)

line_a.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)
line_b.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)

print("Starting Pi5 signal test...")

try:
    while True:
        line_a.set_value(1)
        line_b.set_value(0)
        time.sleep(0.000058)

        line_a.set_value(0)
        line_b.set_value(1)
        time.sleep(0.000058)

except KeyboardInterrupt:
    line_a.set_value(0)
    line_b.set_value(0)
    print("Stopped")