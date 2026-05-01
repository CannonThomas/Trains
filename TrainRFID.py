# TrainRFID.py
#
# Multi-reader RC522 RFID driver using lgpio software (bit-bang) SPI.
# No spidev or dtoverlay required.
#
# Python requirements:  pip install lgpio

import time
from collections import deque
import train_config

try:
    import lgpio
    _LGPIO_OK = True
except ImportError:
    _LGPIO_OK = False


# ── Software SPI ──────────────────────────────────────────────────────────────

class _SoftSPI:
    """
    Bit-bang SPI master using lgpio GPIO.
    All readers share one instance (same MOSI/MISO/SCLK pins).
    CS is managed per-reader by the caller.
    """

    def __init__(self, chip, mosi: int, miso: int, sclk: int):
        self.chip = chip
        self.mosi = mosi
        self.miso = miso
        self.sclk = sclk
        lgpio.gpio_claim_output(chip, mosi, 0)
        lgpio.gpio_claim_output(chip, sclk, 0)
        lgpio.gpio_claim_input(chip, miso)

    def xfer(self, cs_pin: int, data: list) -> list:
        """Assert cs_pin low, transfer bytes, deassert. Returns received bytes."""
        result = []
        lgpio.gpio_write(self.chip, cs_pin, 0)
        for byte_out in data:
            byte_in = 0
            for bit in range(7, -1, -1):
                lgpio.gpio_write(self.chip, self.mosi, (byte_out >> bit) & 1)
                lgpio.gpio_write(self.chip, self.sclk, 1)
                byte_in = (byte_in << 1) | lgpio.gpio_read(self.chip, self.miso)
                lgpio.gpio_write(self.chip, self.sclk, 0)
            result.append(byte_in)
        lgpio.gpio_write(self.chip, cs_pin, 1)
        return result

    def cleanup(self):
        for pin in (self.mosi, self.miso, self.sclk):
            try:
                lgpio.gpio_free(self.chip, pin)
            except Exception:
                pass


# ── Minimal MFRC522 driver ────────────────────────────────────────────────────

class _MFRC522:
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

    PICC_REQIDL   = 0x26
    PICC_ANTICOLL = 0x93

    MI_OK  = 0
    MI_ERR = 2

    def __init__(self, spi: _SoftSPI, chip, cs_pin: int, rst_pin: int):
        self.spi  = spi
        self.chip = chip
        self.cs   = cs_pin
        self.rst  = rst_pin

    def _write(self, reg: int, val: int):
        self.spi.xfer(self.cs, [(reg << 1) & 0x7E, val & 0xFF])

    def _read(self, reg: int) -> int:
        return self.spi.xfer(self.cs, [((reg << 1) & 0x7E) | 0x80, 0x00])[1]

    def _set_bits(self, reg, mask):
        self._write(reg, self._read(reg) | mask)

    def _clear_bits(self, reg, mask):
        self._write(reg, self._read(reg) & (~mask & 0xFF))

    def init(self):
        lgpio.gpio_write(self.chip, self.rst, 1)
        time.sleep(0.05)
        self._write(self.CommandReg,    self.PCD_RESETPHASE)
        time.sleep(0.05)
        self._write(self.TModeReg,      0x8D)
        self._write(self.TPrescalerReg, 0x3E)
        self._write(self.TReloadRegL,   30)
        self._write(self.TReloadRegH,   0)
        self._write(self.TxASKReg,      0x40)
        self._write(self.ModeReg,       0x3D)
        self._set_bits(self.TxControlReg, 0x03)

    def _to_card(self, command: int, send_data: list):
        irq_en   = 0x77 if command == self.PCD_TRANSCEIVE else 0x00
        wait_irq = 0x30 if command == self.PCD_TRANSCEIVE else 0x00

        self._write(self.CommIEnReg,  irq_en | 0x80)
        self._clear_bits(self.CommIrqReg, 0x80)
        self._set_bits(self.FIFOLevelReg, 0x80)
        self._write(self.CommandReg,  self.PCD_IDLE)
        for b in send_data:
            self._write(self.FIFODataReg, b)
        self._write(self.CommandReg, command)
        if command == self.PCD_TRANSCEIVE:
            self._set_bits(self.BitFramingReg, 0x80)

        i = 2000
        while i > 0:
            n = self._read(self.CommIrqReg)
            if n & wait_irq:
                break
            if n & 0x01:
                break
            i -= 1

        self._clear_bits(self.BitFramingReg, 0x80)

        if i == 0 or self._read(self.ErrorReg) & 0x1B:
            return (self.MI_ERR, [], 0)

        irq = self._read(self.CommIrqReg)
        if irq & irq_en & 0x01:
            return (self.MI_ERR, [], 0)

        n_bytes  = self._read(self.FIFOLevelReg)
        last_bits = self._read(self.ControlReg) & 0x07
        back_bits = ((n_bytes - 1) * 8 + last_bits) if last_bits else n_bytes * 8
        n_bytes   = max(1, min(n_bytes, 16))
        back_data = [self._read(self.FIFODataReg) for _ in range(n_bytes)]
        return (self.MI_OK, back_data, back_bits)

    def _request(self) -> int:
        self._write(self.BitFramingReg, 0x07)
        status, _, back_bits = self._to_card(self.PCD_TRANSCEIVE, [self.PICC_REQIDL])
        return self.MI_OK if (status == self.MI_OK and back_bits == 0x10) else self.MI_ERR

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
    def __init__(self, logger=print):
        self.logger = logger
        self.mock_queue: deque = deque()
        self._readers: list = []
        self._spi: _SoftSPI = None
        self._chip = None
        self._ready = False

    def _is_mock(self) -> bool:
        return train_config.MOCK_MODE or not _LGPIO_OK

    def _ensure_ready(self) -> bool:
        if self._ready:
            return True
        if self._is_mock():
            if not _LGPIO_OK:
                self.logger("[RFID] lgpio not available — mock mode")
            self._ready = True
            return True
        try:
            self._chip = lgpio.gpiochip_open(train_config.GPIO_CHIP)

            self._spi = _SoftSPI(
                self._chip,
                mosi=train_config.SPI_MOSI,
                miso=train_config.SPI_MISO,
                sclk=train_config.SPI_SCLK,
            )

            for cfg in train_config.RFID_READERS:
                cs, rst = cfg["cs"], cfg["rst"]
                lgpio.gpio_claim_output(self._chip, cs,  1)
                lgpio.gpio_claim_output(self._chip, rst, 1)
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

    def scan_all(self, timeout_sec: float = 0.25):
        """Poll all readers. Returns (reader_index, uid_str) or (None, None)."""
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
        """Poll one reader. Returns uid_str or None."""
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
        uid_upper = uid.upper()
        for name, info in train_config.CAR_ROSTER.items():
            if info["rfid"].upper() == uid_upper:
                return name
        return None

    def get_default_track(self, uid: str):
        name = self.identify_car(uid)
        return train_config.CAR_ROSTER[name]["default_track"] if name else None

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        if self._spi:
            try:
                self._spi.cleanup()
            except Exception:
                pass
        if self._chip is not None:
            for cfg in train_config.RFID_READERS:
                for pin in (cfg["cs"], cfg["rst"]):
                    try:
                        lgpio.gpio_free(self._chip, pin)
                    except Exception:
                        pass
            try:
                lgpio.gpiochip_close(self._chip)
            except Exception:
                pass
        self._ready = False
        self.logger("[RFID] Cleanup complete")
