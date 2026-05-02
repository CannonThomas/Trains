import lgpio, time

CHIP = 0  # try chip 0 instead of 4
PIN = 13

h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, PIN, 0)

print(f"Toggling GPIO{PIN} on chip {CHIP} every 1s. Ctrl+C to stop.\n")
try:
    while True:
        lgpio.gpio_write(h, PIN, 1)
        rb = lgpio.gpio_read(h, PIN)
        print(f"HIGH -> readback={rb}")
        time.sleep(1)
        lgpio.gpio_write(h, PIN, 0)
        rb = lgpio.gpio_read(h, PIN)
        print(f"LOW  -> readback={rb}")
        time.sleep(1)
except KeyboardInterrupt:
    lgpio.gpio_write(h, PIN, 0)
    lgpio.gpiochip_close(h)
