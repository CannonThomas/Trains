import lgpio, time

CHIP = 4
PIN = 12

h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, PIN, 0)

info = lgpio.gpio_get_chip_info(h)
print(f"Chip {CHIP} info: {info}")
print(f"Toggling GPIO{PIN} (pin 32) every 1s. Ctrl+C to stop.\n")

try:
    while True:
        lgpio.gpio_write(h, PIN, 1)
        readback = lgpio.gpio_read(h, PIN)
        print(f"WROTE HIGH -> readback={readback}  {'OK' if readback==1 else 'FAIL'}")
        time.sleep(1)

        lgpio.gpio_write(h, PIN, 0)
        readback = lgpio.gpio_read(h, PIN)
        print(f"WROTE LOW  -> readback={readback}  {'OK' if readback==0 else 'FAIL'}")
        time.sleep(1)
except KeyboardInterrupt:
    lgpio.gpio_write(h, PIN, 0)
    lgpio.gpiochip_close(h)
    print("done")
