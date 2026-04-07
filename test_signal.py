import gpiod
import time

# Pins
PIN_A = 23  # IN1
PIN_B = 24  # IN2
PIN_EN = 18 # ENA

chip = gpiod.Chip("gpiochip4")

line_a = chip.get_line(PIN_A)
line_b = chip.get_line(PIN_B)
line_en = chip.get_line(PIN_EN)

line_a.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)
line_b.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)
line_en.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)

# 🔥 TURN ON H-BRIDGE
line_en.set_value(1)

print("Running signal test...")

try:
    while True:
        # polarity A
        line_a.set_value(1)
        line_b.set_value(0)
        time.sleep(0.001)

        # polarity B
        line_a.set_value(0)
        line_b.set_value(1)
        time.sleep(0.001)

except KeyboardInterrupt:
    print("Stopped")
    line_a.set_value(0)
    line_b.set_value(0)
    line_en.set_value(0)