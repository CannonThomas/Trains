# rfid_diag.py - run this on the Pi to diagnose RFID setup issues
import os, glob, subprocess

print("=" * 50)
print("1. SPI devices")
devs = glob.glob("/dev/spidev*")
if devs:
    for d in devs:
        print(f"   FOUND: {d}")
else:
    print("   NONE FOUND - SPI is not enabled!")
    print("   Fix: run  sudo raspi-config  -> Interface Options -> SPI -> Enable")

print()
print("2. GPIO chips")
chips = glob.glob("/dev/gpiochip*")
for c in chips:
    print(f"   {c}")

print()
print("3. config.txt SPI overlays")
try:
    with open("/boot/firmware/config.txt") as f:
        lines = [l.strip() for l in f if "spi" in l.lower() and not l.strip().startswith("#")]
    if lines:
        for l in lines:
            print(f"   {l}")
    else:
        print("   No SPI lines found in config.txt")
except Exception as e:
    print(f"   Could not read config.txt: {e}")

print()
print("4. lgpio test")
try:
    import lgpio
    for chip_num in [4, 0, 1, 2, 3]:
        try:
            h = lgpio.gpiochip_open(chip_num)
            lgpio.gpiochip_close(h)
            print(f"   gpiochip{chip_num}: OK")
        except Exception as e:
            print(f"   gpiochip{chip_num}: {e}")
except ImportError:
    print("   lgpio not installed")

print()
print("5. spidev test")
try:
    import spidev
    spi = spidev.SpiDev()
    try:
        spi.open(0, 0)
        print("   spidev(0,0): OK")
        try:
            spi.no_cs = True
            print("   no_cs=True: supported")
        except Exception as e:
            print(f"   no_cs=True: NOT supported ({e})")
        spi.close()
    except Exception as e:
        print(f"   spidev(0,0): FAILED - {e}")
except ImportError:
    print("   spidev not installed")

print()
print("6. Claiming CS pins with lgpio")
try:
    import lgpio
    import train_config
    h = lgpio.gpiochip_open(train_config.GPIO_CHIP)
    for cfg in train_config.RFID_READERS:
        try:
            lgpio.gpio_claim_output(h, cfg["cs"], 1)
            lgpio.gpio_free(h, cfg["cs"])
            print(f"   GPIO{cfg['cs']} (CS {cfg['name']}): OK")
        except Exception as e:
            print(f"   GPIO{cfg['cs']} (CS {cfg['name']}): FAILED - {e}")
        try:
            lgpio.gpio_claim_output(h, cfg["rst"], 1)
            lgpio.gpio_free(h, cfg["rst"])
            print(f"   GPIO{cfg['rst']} (RST {cfg['name']}): OK")
        except Exception as e:
            print(f"   GPIO{cfg['rst']} (RST {cfg['name']}): FAILED - {e}")
    lgpio.gpiochip_close(h)
except Exception as e:
    print(f"   Could not open gpiochip: {e}")

print("=" * 50)
