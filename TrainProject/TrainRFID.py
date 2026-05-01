# TrainRFID.py

from collections import deque
from train_config import CAR_ROSTER, MOCK_MODE, RFID_READERS


class TrainRFID:
    """
    4-reader RFID handler.

    Reader locations:
    - RFID0_ENTRY
    - RFID1_S1
    - RFID2_S2
    - RFID3_S3
    """

    def __init__(self, logger=print):
        self.logger = logger

        self.rfid_to_car = {
            info["rfid"]: car_name
            for car_name, info in CAR_ROSTER.items()
        }

        self.mock_queues = {
            reader_name: deque()
            for reader_name in RFID_READERS
        }

    def log(self, msg):
        self.logger(msg)

    def enqueue_mock_car(self, reader_name, car_name):
        if reader_name not in self.mock_queues:
            self.log(f"[RFID WARN] Unknown reader: {reader_name}")
            return

        if car_name not in CAR_ROSTER:
            self.log(f"[RFID WARN] Unknown car: {car_name}")
            return

        tag = CAR_ROSTER[car_name]["rfid"]
        self.mock_queues[reader_name].append(tag)

    def read_reader(self, reader_name):
        if reader_name not in RFID_READERS:
            self.log(f"[RFID WARN] Unknown reader: {reader_name}")
            return None

        if MOCK_MODE:
            if self.mock_queues[reader_name]:
                tag = self.mock_queues[reader_name].popleft()
                self.log(f"[MOCK RFID] {reader_name} read tag {tag}")
                return tag
            return None

        # Real MFRC522 code goes here later
        return None

    def scan_all(self):
        detections = {}

        for reader_name in RFID_READERS:
            tag = self.read_reader(reader_name)

            if tag:
                detections[reader_name] = {
                    "tag": tag,
                    "car": self.rfid_to_car.get(tag),
                }

        return detections