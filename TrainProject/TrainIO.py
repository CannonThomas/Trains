class TrainIO:
    def set_turnout(self, track):
        print(f"[TURNOUT] Switching to track {track}")

    def crossing_on(self):
        print("[CROSSING] Lights ON, gate DOWN")

    def crossing_off(self):
        print("[CROSSING] Lights OFF, gate UP")