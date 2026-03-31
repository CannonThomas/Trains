from collections import deque
import time
import train_config
from train_config import CAR_ROSTER

try:
    from mfrc522 import MFRC522 as _MFRC522
    _MFRC522_AVAILABLE = True
except ImportError:
    _MFRC522_AVAILABLE = False


class TrainRFID:
    """
    Fixed-roster RFID handler.
    In mock mode, it returns tags from a queue you control.
    In real mode, it polls an MFRC522 reader over SPI.
    """

    def __init__(self, logger=print):
        self.logger = logger
        self.mock_queue = deque()
        self.last_tag = None
        self.rfid_to_car = {info["rfid"]: car_name for car_name, info in CAR_ROSTER.items()}
        self._reader = None

    def log(self, msg: str):
        self.logger(msg)

    def _ensure_reader(self):
        if self._reader is None and _MFRC522_AVAILABLE:
            self._reader = _MFRC522()

    def enqueue_mock_tag(self, tag: str) -> None:
        if tag in self.rfid_to_car:
            self.mock_queue.append(tag)

    def enqueue_mock_car(self, car_name: str) -> None:
        car = CAR_ROSTER.get(car_name)
        if car:
            self.mock_queue.append(car["rfid"])

    def read_tag(self, timeout_sec: float = 0.25):
        """
        Returns tag UID as uppercase hex string (example: 'DEADBEEF'),
        or None if no tag is seen within timeout_sec.
        """
        if train_config.MOCK_MODE:
            if self.mock_queue:
                self.last_tag = self.mock_queue.popleft()
                self.log(f"[MOCK RFID] Read tag: {self.last_tag}")
                return self.last_tag
            return None

        self._ensure_reader()
        if self._reader is None:
            self.log("[RFID] MFRC522 library not available")
            return None

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            status, _ = self._reader.MFRC522_Request(self._reader.PICC_REQIDL)
            if status == self._reader.MI_OK:
                status, uid = self._reader.MFRC522_Anticoll()
                if status == self._reader.MI_OK and uid:
                    tag = "".join(f"{b:02X}" for b in uid[:4])
                    self.last_tag = tag
                    self.log(f"[RFID] Read tag: {tag}")
                    return tag
            time.sleep(0.02)

        return None

    def identify_car(self, tag: str):
        if not tag:
            return None
        return self.rfid_to_car.get(tag)

    def get_default_track(self, tag: str):
        car_name = self.identify_car(tag)
        if not car_name:
            return None
        return CAR_ROSTER[car_name]["default_track"]