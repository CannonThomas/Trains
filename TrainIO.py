# TrainIO.py
import time
import train_config
from TrainDCC import TrainDCC

try:
    from TrainMock import TrainMock
except ImportError:
    TrainMock = None

try:
    import lgpio
except ImportError:
    lgpio = None


class TrainIO:
    def __init__(self, logger=print):
        self.logger = logger
        self.mock_mode = train_config.MOCK_MODE

        self.chip = None
        self.pin_map = train_config.GPIO_PINS
        self.dcc_pin_map = train_config.DCC_PINS

        if self.mock_mode:
            self.dcc = None
            self.mock = TrainMock(logger=self.logger) if TrainMock else None
            self.logger("[IO] MOCK_MODE enabled")
            return

        self.mock = None

        self.dcc = TrainDCC(
            pin_a=self.dcc_pin_map["IN1"],
            pin_b=self.dcc_pin_map["IN2"],
            pin_en=self.dcc_pin_map["ENA"],
            loco_address=train_config.LOCO_ADDRESS,
            logger=self.logger
        )
        self.dcc.setup()

        if lgpio is None:
            raise RuntimeError("lgpio is required for real hardware mode")

        self.chip = lgpio.gpiochip_open(0)

        for name, pin in self.pin_map.items():
            lgpio.gpio_claim_output(self.chip, pin, 0)

        self.logger("[IO] Real hardware initialized")

    def _write_pin(self, name, value):
        if self.mock_mode:
            self.logger(f"[MOCK IO] {name} -> {value}")
            return
        lgpio.gpio_write(self.chip, self.pin_map[name], value)

    # -----------------------------
    # DCC helpers
    # -----------------------------
    def dcc_idle(self):
        if self.mock_mode:
            self.logger("[MOCK DCC] idle")
            return
        self.dcc.dcc_idle()

    def dcc_loco_speed(self, address, speed, forward=True):
        if self.mock_mode:
            direction = "forward" if forward else "reverse"
            self.logger(f"[MOCK DCC] addr={address} speed={speed} dir={direction}")
            return

        self.dcc.set_address(address)

        if speed <= 0:
            self.dcc.stop()
        else:
            if forward:
                self.dcc.forward(speed)
            else:
                self.dcc.reverse(speed)

    def dcc_power_off(self):
        if self.mock_mode:
            self.logger("[MOCK DCC] power off")
            return
        self.dcc.power_off()

    # -----------------------------
    # Routing / turnout helpers
    # -----------------------------
    def route_to_main_from_loop(self):
        self._write_pin("LOOP", 0)
        self.logger("[IO] Victory Lap -> Main sorting line")

    def route_to_victory_lap(self):
        self._write_pin("LOOP", 1)
        self.logger("[IO] Routed to Victory Lap")

    def route_to_track(self, track):
        self.route_to_main_from_loop()

        if track == 1:
            self._write_pin("S1", 1)
            self._write_pin("S2", 0)
            self._write_pin("S3", 0)
        elif track == 2:
            self._write_pin("S1", 1)
            self._write_pin("S2", 1)
            self._write_pin("S3", 0)
        elif track == 3:
            self._write_pin("S1", 0)
            self._write_pin("S2", 1)
            self._write_pin("S3", 0)
        elif track == 4:
            self._write_pin("S1", 0)
            self._write_pin("S2", 0)
            self._write_pin("S3", 0)
        else:
            self.logger(f"[WARN] Invalid track route request: {track}")
            return

        self.logger(f"[IO] Routed to Track {track}")

    def set_all_default(self):
        self._write_pin("LOOP", 0)
        self._write_pin("S1", 0)
        self._write_pin("S2", 0)
        self._write_pin("S3", 0)
        self.logger("[IO] Turnouts reset to default")

    def set_crossing(self, enabled):
        state = "ON" if enabled else "OFF"
        self.logger(f"[IO] Crossing {state}")

    def decouple(self, pulse_sec=0.25):
        if self.mock_mode:
            self.logger("[MOCK IO] Decouple pulse")
            return

        self._write_pin("DECOUPLE", 1)
        self.logger("[IO] Decouple ON")
        time.sleep(pulse_sec)
        self._write_pin("DECOUPLE", 0)
        self.logger("[IO] Decouple OFF")

    def cleanup(self):
        if self.mock_mode:
            self.logger("[IO] Mock cleanup complete")
            return

        try:
            self.set_all_default()
        except Exception:
            pass

        try:
            self._write_pin("DECOUPLE", 0)
        except Exception:
            pass

        try:
            if self.dcc is not None:
                self.dcc.power_off()
                self.dcc.cleanup()
        except Exception as e:
            self.logger(f"[WARN] DCC cleanup failed: {e}")

        if self.chip is not None:
            try:
                for pin in self.pin_map.values():
                    try:
                        lgpio.gpio_free(self.chip, pin)
                    except Exception:
                        pass
                lgpio.gpiochip_close(self.chip)
            except Exception as e:
                self.logger(f"[WARN] GPIO cleanup failed: {e}")

        self.chip = None
        self.logger("[IO] Cleanup complete")