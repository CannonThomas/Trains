import RPi.GPIO as GPIO
import time

# Use BCM numbering
GPIO.setmode(GPIO.BCM)

# Choose your pins (CHANGE if needed)
PIN_A = 23  # IN1
PIN_B = 24  # IN2

GPIO.setup(PIN_A, GPIO.OUT)
GPIO.setup(PIN_B, GPIO.OUT)

print("Starting signal test...")

try:
    while True:
        # State 1
        GPIO.output(PIN_A, 1)
        GPIO.output(PIN_B, 0)
        time.sleep(0.000058)  # ~58 microseconds

        # State 2 (flip polarity)
        GPIO.output(PIN_A, 0)
        GPIO.output(PIN_B, 1)
        time.sleep(0.000058)

except KeyboardInterrupt:
    print("Stopping...")
    GPIO.cleanup()