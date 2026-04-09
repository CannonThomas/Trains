# TrainDCC.py
import lgpio
import time
import threading
from collections import namedtuple


class TrainDCC:
    ONE_US = 58
    ZERO_US = 116
    REFRESH_SEC = 0.03  # resend current command every 30 ms

    Pulse = namedtuple("Pulse", ["group_bits", "group_mask", "pulse_delay"])

    def __init__(self, pin_a=23, pin_b=24, pin_en=18, loco_address=3, logger=print):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.pin_en = pin_en
        self.loco_address = loco_address
        self.logger = logger

        self.h = None
        self.write = None
        self.group_leader = pin_a

        self._lock = threading.Lock()
        self._running = False
        self._refresh_thread = None

        # "off" means no waveform output at all
        self._current_mode = "off"   # off, idle, stop, forward, reverse
        self._current_speed = 0
        self._current_repeat = 6

    # -------------------------------------------------
    # GPIO setup / cleanup
    # -------------------------------------------------
    def setup(self):
        if self.h is not None:
            return

        self.h = lgpio.gpiochip_open(0)

        # ENA as normal output
        lgpio.gpio_claim_output(self.h, self.pin_en, 0)

        # complementary DCC pins as a group
        lgpio.group_claim_output(self.h, [self.pin_a, self.pin_b], [0, 0])

        self.write = lgpio.gpio_write

        # enable H-bridge but keep both inputs LOW until commanded
        self.write(self.h, self.pin_en, 1)
        self._set_outputs_low()

        self._running = True
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()

        self.logger(f"[DCC] Ready (IN1={self.pin_a}, IN2={self.pin_b}, ENA={self.pin_en})")

    def cleanup(self):
        self._running = False

        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=0.2)
            self._refresh_thread = None

        if self.h is None:
            return

        try:
            lgpio.tx_wave(self.h, self.group_leader, [])
        except Exception:
            pass

        try:
            self._set_outputs_low()
        except Exception:
            pass

        try:
            self.write(self.h, self.pin_en, 0)
        except Exception:
            pass

        try:
            lgpio.group_free(self.h, self.group_leader)
        except Exception:
            pass

        try:
            lgpio.gpio_free(self.h, self.pin_en)
        except Exception:
            pass

        try:
            lgpio.gpiochip_close(self.h)
        except Exception:
            pass

        self.h = None
        self.logger("[DCC] GPIO cleaned up")

    def _set_outputs_low(self):
        if self.h is None:
            return
        # mask 0b11 means update both pins, bits 0b00 means both LOW
        lgpio.group_write(self.h, self.group_leader, 0b00, 0b11)

    # -------------------------------------------------
    # DCC packet helpers
    # -------------------------------------------------
    @staticmethod
    def build_dcc_packet(address, data):
        checksum = address ^ data
        return [address, data, checksum]

    @staticmethod
    def byte_to_bits(byte):
        return [(byte >> i) & 1 for i in range(7, -1, -1)]

    def build_bitstream(self, packet):
        bits = []
        bits += [1] * 14  # preamble

        for byte in packet:
            bits.append(0)  # start bit
            bits += self.byte_to_bits(byte)

        bits.append(1)  # packet end bit
        return bits

    # -------------------------------------------------
    # Waveform helpers
    # -------------------------------------------------
    def _dcc_bit_pulses(self, us):
        # group order is exactly [pin_a, pin_b]
        # bit 0 -> pin_a (IN1)
        # bit 1 -> pin_b (IN2)
        return [
            self.Pulse(1 << 0, 0b11, us),  # IN1=1, IN2=0
            self.Pulse(1 << 1, 0b11, us),  # IN1=0, IN2=1
        ]

    def bitstream_to_pulses(self, bits):
        pulses = []
        for bit in bits:
            if bit == 1:
                pulses.extend(self._dcc_bit_pulses(self.ONE_US))
            else:
                pulses.extend(self._dcc_bit_pulses(self.ZERO_US))
        return pulses

    def _send_pulses(self, pulses):
        if self.h is None:
            self.setup()

        while lgpio.tx_room(self.h, self.group_leader, lgpio.TX_WAVE) <= 0:
            time.sleep(0.001)

        lgpio.tx_wave(self.h, self.group_leader, pulses)

        while lgpio.tx_busy(self.h, self.group_leader, lgpio.TX_WAVE):
            time.sleep(0.001)

    def send_bitstream(self, bits, repeat=1):
        pulses = self.bitstream_to_pulses(bits)
        for _ in range(repeat):
            self._send_pulses(pulses)

    def send_packet(self, address, data, repeat=3):
        packet = self.build_dcc_packet(address, data)
        bits = self.build_bitstream(packet)
        self.send_bitstream(bits, repeat=repeat)

    # -------------------------------------------------
    # 28-step speed packet helper
    # -------------------------------------------------
    @staticmethod
    def _speed_28_step_data(step, forward=True):
        step = max(0, min(28, step))

        if step == 0:
            return 0b01000000  # stop

        enc = step + 3
        c_bit = enc & 0x01
        s_nibble = (enc >> 1) & 0x0F
        direction_bit = 0x20 if forward else 0x00

        return 0x40 | direction_bit | (c_bit << 4) | s_nibble

    @staticmethod
    def _map_raw_speed_to_step28(speed):
        speed = max(0, min(126, speed))
        if speed == 0:
            return 0
        return max(1, min(28, int(round(speed * 28 / 126))))

    # -------------------------------------------------
    # Background resend loop
    # -------------------------------------------------
    def _refresh_loop(self):
        while self._running:
            try:
                with self._lock:
                    mode = self._current_mode
                    speed = self._current_speed
                    repeat = self._current_repeat

                if mode == "off":
                    self._set_outputs_low()

                elif mode == "idle":
                    self._send_idle_once(repeat=repeat)

                elif mode == "stop":
                    self._send_stop_once(repeat=repeat)

                elif mode == "forward":
                    self._send_forward_once(speed=speed, repeat=repeat)

                elif mode == "reverse":
                    self._send_reverse_once(speed=speed, repeat=repeat)

            except Exception as e:
                self.logger(f"[DCC] Refresh loop error: {e}")

            time.sleep(self.REFRESH_SEC)

    # -------------------------------------------------
    # One-shot packet send helpers
    # -------------------------------------------------
    def _send_idle_once(self, repeat=3):
        self.send_packet(0xFF, 0x00, repeat=repeat)

    def _send_stop_once(self, repeat=8):
        data = self._speed_28_step_data(0, True)
        self.send_packet(self.loco_address, data, repeat=repeat)

    def _send_forward_once(self, speed=10, repeat=8):
        step28 = self._map_raw_speed_to_step28(speed)
        data = self._speed_28_step_data(step28, True)
        self.send_packet(self.loco_address, data, repeat=repeat)

    def _send_reverse_once(self, speed=10, repeat=8):
        step28 = self._map_raw_speed_to_step28(speed)
        data = self._speed_28_step_data(step28, False)
        self.send_packet(self.loco_address, data, repeat=repeat)

    # -------------------------------------------------
    # Public command state setters
    # -------------------------------------------------
    def off(self):
        with self._lock:
            self._current_mode = "off"
            self._current_speed = 0
            self._current_repeat = 0
        self._set_outputs_low()
        self.logger("[DCC] outputs off")

    def dcc_idle(self, repeat=3):
        with self._lock:
            self._current_mode = "idle"
            self._current_speed = 0
            self._current_repeat = repeat
        self.logger("[DCC] idle mode set")

    def stop(self, repeat=8):
        with self._lock:
            self._current_mode = "stop"
            self._current_speed = 0
            self._current_repeat = repeat
        self.logger("[DCC] stop mode set")

    def forward(self, speed=20, repeat=8):
        with self._lock:
            self._current_mode = "forward"
            self._current_speed = speed
            self._current_repeat = repeat
        step28 = self._map_raw_speed_to_step28(speed)
        data = self._speed_28_step_data(step28, True)
        self.logger(f"[DCC] forward mode set: raw={speed}, step28={step28}, data=0x{data:02X}")

    def reverse(self, speed=20, repeat=8):
        with self._lock:
            self._current_mode = "reverse"
            self._current_speed = speed
            self._current_repeat = repeat
        step28 = self._map_raw_speed_to_step28(speed)
        data = self._speed_28_step_data(step28, False)
        self.logger(f"[DCC] reverse mode set: raw={speed}, step28={step28}, data=0x{data:02X}")

    # -------------------------------------------------
    # Continuous scope test
    # -------------------------------------------------
    def build_test_wave(self):
        pulses = []

        for _ in range(20):
            pulses.extend(self._dcc_bit_pulses(self.ONE_US))

        pulses.extend(self._dcc_bit_pulses(self.ZERO_US))
        return pulses

    def test_signal(self):
        if self.h is None:
            self.setup()

        self.logger("[DCC] Running tx_wave test... Ctrl+C to stop")

        try:
            while True:
                self._send_pulses(self.build_test_wave())
        except KeyboardInterrupt:
            self.logger("[DCC] Test stopped")