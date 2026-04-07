import gpiod
import time

PIN_A = 23  # IN1
PIN_B = 24  # IN2

chip = gpiod.Chip("gpiochip4")

line_a = chip.get_line(PIN_A)
line_b = chip.get_line(PIN_B)

line_a.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)
line_b.request(consumer="dcc", type=gpiod.LINE_REQ_DIR_OUT)

# --- DCC TIMING ---
ONE = 58e-6
ZERO = 116e-6

def set_polarity(a, b):
    line_a.set_value(a)
    line_b.set_value(b)

def send_half_cycle(duration):
    # polarity A
    set_polarity(1, 0)
    time.sleep(duration)

    # polarity B
    set_polarity(0, 1)
    time.sleep(duration)

def send_bit(bit):
    if bit == 1:
        send_half_cycle(ONE)
    else:
        send_half_cycle(ZERO)

def byte_to_bits(byte):
    return [(byte >> i) & 1 for i in range(7, -1, -1)]

def send_packet(address, data):
    checksum = address ^ data

    # PREAMBLE (14 ones)
    for _ in range(14):
        send_bit(1)

    # START BIT
    send_bit(0)

    # ADDRESS
    for b in byte_to_bits(address):
        send_bit(b)

    # START BIT
    send_bit(0)

    # DATA
    for b in byte_to_bits(data):
        send_bit(b)

    # START BIT
    send_bit(0)

    # CHECKSUM
    for b in byte_to_bits(checksum):
        send_bit(b)

    # END BIT
    send_bit(1)

print("Sending DCC packets... Ctrl+C to stop")

try:
    while True:
        send_packet(3, 104)  # address 3, forward
except KeyboardInterrupt:
    print("Stopped")
    set_polarity(0, 0)