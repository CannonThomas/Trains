import lgpio, time

h = lgpio.gpiochip_open(4)
lgpio.gpio_claim_output(h, 12, 0)

print("Toggling GPIO12 (pin 32) every 1s. Ctrl+C to stop.")
try:
    while True:
        lgpio.gpio_write(h, 12, 1)
        print("HIGH (3.3V)")
        time.sleep(1)
        lgpio.gpio_write(h, 12, 0)
        print("LOW (0V)")
        time.sleep(1)
except KeyboardInterrupt:
    lgpio.gpio_write(h, 12, 0)
    lgpio.gpiochip_close(h)
    print("done")
