"""
Standalone PWM test for GPIO18 (L298 ENA pin).
Probe pin 12 with multimeter — should see avg voltage step up:
   0%  -> ~0.0V
  25%  -> ~0.8V
  50%  -> ~1.6V
  75%  -> ~2.5V
  100% -> ~3.3V
"""
import lgpio, time

CHIP = 0
PIN  = 18         # GPIO18 = L298 ENA
FREQ = 1000       # 1 kHz

h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, PIN, 0)

print(f"Sweeping PWM on GPIO{PIN} @ {FREQ} Hz")
print("Probe pin 12 (GPIO18) with multimeter.\n")

try:
    for duty in (0, 25, 50, 75, 100):
        lgpio.tx_pwm(h, PIN, FREQ, duty)
        print(f"  duty = {duty}%  (expect ~{duty/100*3.3:.2f}V on meter)")
        time.sleep(4)
    print("\nDone. Setting LOW.")
    lgpio.tx_pwm(h, PIN, 0, 0)
    lgpio.gpio_write(h, PIN, 0)
finally:
    lgpio.gpiochip_close(h)
