# TrainRFID.py

from collections import deque
from train_config import CAR_ROSTER, MOCK_MODE


class TrainRFID:
    """
    Fixed-roster RFID handler.
    In mock mode, it returns tags from a queue you control.
    """

    def __init__(self):
        self.mock_queue = deque()
        self.last_tag = None
        self.rfid_to_car = {info["rfid"]: car_name for car_name, info in CAR_ROSTER.items()}

    def enqueue_mock_tag(self, tag: str) -> None:
        if tag in self.rfid_to_car:
            self.mock_queue.append(tag)

    def enqueue_mock_car(self, car_name: str) -> None:
        car = CAR_ROSTER.get(car_name)
        if car:
            self.mock_queue.append(car["rfid"])

    def read_tag(self):
        """
        Replace the real section with MFRC522 or your actual RFID reader code.
        """
        if MOCK_MODE:
            if self.mock_queue:
                self.last_tag = self.mock_queue.popleft()
                return self.last_tag
            return None

        # Real RFID code goes here
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