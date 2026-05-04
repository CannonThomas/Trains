"""
Direct test for the IN2 wire (GPIO23 → L298 IN2).
Holds GPIO23 HIGH for 5s, then LOW for 5s, repeating.

While HIGH: probe pin 16 (Pi side) AND L298 IN2 input pin (board side).
   Pi pin 16 should read 3.3V.
   L298 IN2 input should read 3.3V.
If Pi side = 3.3V but L298 side = 0V, the wire is broken/loose.
"""
import lgpio, time

CHIP = 0
PIN  = 23  # TRACK_IN2_PIN

h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, PIN, 0)

print(f"Toggling GPIO{PIN} (pin 16) every 5s. Probe pin 16 AND L298 IN2.\nCtrl+C to stop.\n")

try:
    while True:
        lgpio.gpio_write(h, PIN, 1)
        print(f"GPIO{PIN} HIGH — should be 3.3V on pin 16 and L298 IN2")
        time.sleep(5)
        lgpio.gpio_write(h, PIN, 0)
        print(f"GPIO{PIN} LOW  — should be 0V")
        time.sleep(5)
except KeyboardInterrupt:
    lgpio.gpio_write(h, PIN, 0)
    lgpio.gpiochip_close(h)
    print("done")
