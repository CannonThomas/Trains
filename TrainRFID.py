# TrainRFID.py
#
# Multi-reader RC522 RFID driver.
# All four readers share one SPI bus (MOSI/MISO/SCLK).
# Each reader's CS and RST pins are driven manually via lgpio.
#
# System requirement:
#   Add  dtoverlay=spi0-0cs  to /boot/firmware/config.txt so the kernel SPI
#   driver does not claim any hardware CE pin, leaving all CS lines free for
#   lgpio.  Reboot after making that change.
#
# Python requirements:
#   pip install spidev lgpio

import time
from collections import deque
import train_config

try:
    import spidev
    _SPIDEV_OK = True
except ImportError:
    _SPIDEV_OK = False

try:
    import lgpio
    _LGPIO_OK = True
except ImportError:
    _LGPIO_OK = False


# ── Minimal MFRC522 SPI driver ────────────────────────────────────────────────

class _MFRC522:
    """
    Drives one MFRC522 reader over a shared spidev handle.
    CS and RST pins are managed externally via lgpio.
    """

    # Register map (6-bit addresses)
    CommandReg    = 0x01
    CommIEnReg    = 0x02
    CommIrqReg    = 0x04
    ErrorReg      = 0x06
    FIFODataReg   = 0x09
    FIFOLevelReg  = 0x0A
    ControlReg    = 0x0C
    BitFramingReg = 0x0D
    ModeReg       = 0x11
    TxControlReg  = 0x14
    TxASKReg      = 0x15
    TModeReg      = 0x2A
    TPrescalerReg = 0x2B
    TReloadRegH   = 0x2C
    TReloadRegL   = 0x2D

    PCD_IDLE       = 0x00
    PCD_TRANSCEIVE = 0x0C
    PCD_RESETPHASE = 0x0F

    PICC_REQIDL  = 0x26
    PICC_ANTICOLL = 0x93

    MI_OK  = 0
    MI_ERR = 2

    def __init__(self, spi, chip, cs_pin: int, rst_pin: int):
        self.spi = spi
        self.chip = chip
        self.cs = cs_pin
        self.rst = rst_pin

    # SPI register access ────────────────────────────────────────────────────

    def _write(self, reg: int, val: int):
        lgpio.gpio_write(self.chip, self.cs, 0)
        self.spi.xfer2([(reg << 1) & 0x7E, val & 0xFF])
        lgpio.gpio_write(self.chip, self.cs, 1)

    def _read(self, reg: int) -> int:
        lgpio.gpio_write(self.chip, self.cs, 0)
        r = self.spi.xfer2([((reg << 1) & 0x7E) | 0x80, 0x00])
        lgpio.gpio_write(self.chip, self.cs, 1)
        return r[1]

    def _set_bits(self, reg: int, mask: int):
        self._write(reg, self._read(reg) | mask)

    def _clear_bits(self, reg: int, mask: int):
        self._write(reg, self._read(reg) & (~mask & 0xFF))

    # Initialisation ─────────────────────────────────────────────────────────

    def init(self):
        lgpio.gpio_write(self.chip, self.rst, 1)
        time.sleep(0.05)
        self._write(self.CommandReg, self.PCD_RESETPHASE)
        time.sleep(0.05)
        self._write(self.TModeReg,      0x8D)
        self._write(self.TPrescalerReg, 0x3E)
        self._write(self.TReloadRegL,   30)
        self._write(self.TReloadRegH,    0)
        self._write(self.TxASKReg,      0x40)
        self._write(self.ModeReg,       0x3D)
        self._set_bits(self.TxControlReg, 0x03)   # enable antenna

    # Card communication ──────────────────────────────────────────────────────

    def _to_card(self, command: int, send_data: list):
        """Generic transceive; returns (status, back_data, back_bits)."""
        irq_en   = 0x77 if command == self.PCD_TRANSCEIVE else 0x00
        wait_irq = 0x30 if command == self.PCD_TRANSCEIVE else 0x00

        self._write(self.CommIEnReg,   irq_en | 0x80)
        self._clear_bits(self.CommIrqReg, 0x80)
        self._set_bits(self.FIFOLevelReg, 0x80)   # flush FIFO
        self._write(self.CommandReg, self.PCD_IDLE)

        for b in send_data:
            self._write(self.FIFODataReg, b)

        self._write(self.CommandReg, command)
        if command == self.PCD_TRANSCEIVE:
            self._set_bits(self.BitFramingReg, 0x80)   # StartSend

        i = 2000
        while i > 0:
            n = self._read(self.CommIrqReg)
            if n & wait_irq:
                break
            if n & 0x01:          # timer expired
                break
            i -= 1

        self._clear_bits(self.BitFramingReg, 0x80)

        if i == 0:
            return (self.MI_ERR, [], 0)
        if self._read(self.ErrorReg) & 0x1B:
            return (self.MI_ERR, [], 0)

        irq = self._read(self.CommIrqReg)
        if irq & irq_en & 0x01:           # only timer interrupt — no card
            return (self.MI_ERR, [], 0)

        n_bytes = self._read(self.FIFOLevelReg)
        last_bits = self._read(self.ControlReg) & 0x07
        back_bits = ((n_bytes - 1) * 8 + last_bits) if last_bits else n_bytes * 8
        n_bytes = max(1, min(n_bytes, 16))
        back_data = [self._read(self.FIFODataReg) for _ in range(n_bytes)]
        return (self.MI_OK, back_data, back_bits)

    def _request(self) -> int:
        self._write(self.BitFramingReg, 0x07)
        status, _, back_bits = self._to_card(self.PCD_TRANSCEIVE, [self.PICC_REQIDL])
        if status != self.MI_OK or back_bits != 0x10:
            return self.MI_ERR
        return self.MI_OK

    def _anticoll(self):
        self._write(self.BitFramingReg, 0x00)
        status, data, _ = self._to_card(self.PCD_TRANSCEIVE, [self.PICC_ANTICOLL, 0x20])
        if status == self.MI_OK and len(data) == 5:
            bcc = 0
            for b in data[:4]:
                bcc ^= b
            if bcc == data[4]:
                return (self.MI_OK, data[:4])
        return (self.MI_ERR, [])

    def detect_tag(self):
        """Return 8-char hex UID string, or None if no tag present."""
        if self._request() != self.MI_OK:
            return None
        status, uid = self._anticoll()
        if status != self.MI_OK:
            return None
        return "".join(f"{b:02X}" for b in uid)


# ── Public interface ──────────────────────────────────────────────────────────

class TrainRFID:
    """
    Manages 4 RC522 readers on a shared SPI bus using spidev + lgpio.
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.mock_queue: deque = deque()
        self._readers: list = []
        self._spi = None
        self._chip = None
        self._ready = False

    # ── Initialisation ────────────────────────────────────────────────────────

    def _ensure_ready(self) -> bool:
        if self._ready:
            return True
        if train_config.MOCK_MODE or not _SPIDEV_OK or not _LGPIO_OK:
            if not _SPIDEV_OK or not _LGPIO_OK:
                self.logger("[RFID] spidev/lgpio not available — running in mock mode")
            self._ready = True
            return True
        try:
            self._chip = lgpio.gpiochip_open(train_config.GPIO_CHIP)

            self._spi = spidev.SpiDev()
            self._spi.open(0, 0)            # SPI bus 0, device 0
            self._spi.max_speed_hz = 1_000_000
            self._spi.mode = 0
            self._spi.no_cs = True          # we drive all CS lines manually

            for cfg in train_config.RFID_READERS:
                cs, rst = cfg["cs"], cfg["rst"]
                lgpio.gpio_claim_output(self._chip, cs,  1)   # CS idle-high
                lgpio.gpio_claim_output(self._chip, rst, 1)   # RST active-high
                r = _MFRC522(self._spi, self._chip, cs, rst)
                r.init()
                self._readers.append(r)
                self.logger(f"[RFID] {cfg['name']} ready (CS=GPIO{cs}, RST=GPIO{rst})")

            self._ready = True
            return True
        except Exception as e:
            self.logger(f"[RFID] Init error: {e}")
            return False

    # ── Mock helpers ──────────────────────────────────────────────────────────

    def enqueue_mock_tag(self, uid: str, reader_idx: int = 0):
        self.mock_queue.append((reader_idx, uid))

    def enqueue_mock_car(self, car_name: str, reader_idx: int = 0):
        car = train_config.CAR_ROSTER.get(car_name)
        if car:
            self.mock_queue.append((reader_idx, car["rfid"]))

    # ── Scanning ─────────────────────────────────────────────────────────────

    def _is_mock(self) -> bool:
        return train_config.MOCK_MODE or not _SPIDEV_OK or not _LGPIO_OK

    def scan_all(self, timeout_sec: float = 0.25):
        """
        Poll all readers until a tag is found or timeout expires.
        Returns (reader_index, uid_str) or (None, None).
        """
        if self._is_mock():
            if self.mock_queue:
                idx, uid = self.mock_queue.popleft()
                self.logger(f"[MOCK RFID] {train_config.RFID_READERS[idx]['name']}: {uid}")
                return (idx, uid)
            return (None, None)

        if not self._ensure_ready():
            return (None, None)

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            for i, reader in enumerate(self._readers):
                uid = reader.detect_tag()
                if uid:
                    self.logger(f"[RFID] {train_config.RFID_READERS[i]['name']}: {uid}")
                    return (i, uid)
            time.sleep(0.02)
        return (None, None)

    def scan_reader(self, reader_idx: int, timeout_sec: float = 0.25):
        """Poll a single reader. Returns uid_str or None."""
        if self._is_mock():
            if self.mock_queue:
                idx, uid = self.mock_queue.popleft()
                if idx == reader_idx:
                    return uid
            return None

        if not self._ensure_ready():
            return None

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            uid = self._readers[reader_idx].detect_tag()
            if uid:
                return uid
            time.sleep(0.02)
        return None

    # ── Roster lookups ────────────────────────────────────────────────────────

    def identify_car(self, uid: str):
        """Return car_name for a known UID, or None."""
        uid_upper = uid.upper()
        for name, info in train_config.CAR_ROSTER.items():
            if info["rfid"].upper() == uid_upper:
                return name
        return None

    def get_default_track(self, uid: str):
        name = self.identify_car(uid)
        if not name:
            return None
        return train_config.CAR_ROSTER[name]["default_track"]

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        if self._spi:
            try:
                self._spi.close()
            except Exception:
                pass
        if self._chip is not None:
            for cfg in train_config.RFID_READERS:
                try:
                    lgpio.gpio_free(self._chip, cfg["cs"])
                    lgpio.gpio_free(self._chip, cfg["rst"])
                except Exception:
                    pass
            try:
                lgpio.gpiochip_close(self._chip)
            except Exception:
                pass
        self._ready = False
        self.logger("[RFID] Cleanup complete")
