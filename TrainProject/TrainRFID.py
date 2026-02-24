import random
import time

class TrainRFID:
    def read_tag(self):
        time.sleep(1)
        if random.random() < 0.3:
            return f"TAG_{random.randint(1000, 9999)}"
        return None