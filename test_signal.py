# test_signal.py
import subprocess

ONE_US = 58
ZERO_US = 116

def build_wave():
    pulses = []

    for _ in range(200):
        pulses.append(ONE_US)
        pulses.append(ONE_US)

    for _ in range(20):
        pulses.append(ZERO_US)
        pulses.append(ZERO_US)

    return pulses

pulses = build_wave()

data = "\n".join(str(p) for p in pulses) + "\n"

subprocess.run(
    ["./dcc_tx"],
    input=data,
    text=True
)