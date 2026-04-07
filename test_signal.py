import gpiod
import time

PIN_A = 23
PIN_B = 24

chip = gpiod.Chip("gpiochip4")

line_a = chip.get_line(PIN_A)
line_b = chip.get_line(PIN_B)

line_a.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)
line_b.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)

print("Running signal test... Ctrl+C to stop.")

try:
    while True:
        line_a.set_value(1)
        line_b.set_value(0)
        time.sleep(0.001)

        line_a.set_value(0)
        line_b.set_value(1)
        time.sleep(0.001)

except KeyboardInterrupt:
    print("Stopped")
    line_a.set_value(0)
    line_b.set_value(0)