# TrainDCC.py
import lgpio
import time
import threading
from collections import namedtuple
import train_config


class TrainDCC:
    """
    Pi 5 + lgpio + tx_wave DCC transmitter for one short-address locomotive.

    Uses:
      ENA  -> H-bridge enable
      IN1  -> complementary output A
      IN2  -> complementary output B

    Behavior:
      - no waveform when idle/off until commanded
      - background command-station style resend loop
      - supports idle, stop, forward, reverse
      - short address defaults to 3 for Bachmann
    """

    ONE_US = 58
    ZERO_US = 116

    Pulse = namedtuple("Pulse", ["group_bits", "group_mask", "pulse_delay"])

    def __init__(self, pin_a=23, pin_b=24, pin_en=18, loco_address=3, logger=print):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.pin_en = pin_en
        self.loco_address = loco_address
        self.logger = logger

        self.refresh_sec = train_config.DCC_REFRESH_SEC
        self.packet_repeat = train_config.DCC_PACKET_REPEAT
        self.idle_repeat = train_config.DCC_IDLE_REPEAT

        self.h = None
        self.write = None
        self.group_leader = pin_a

        self._lock = threading.Lock()
        self._running = False
        self._thread = None

        # Command-station state
        self._track_power = False
        self._mode = "off"      # off, idle, stop, forward, reverse
        self._speed = 0
        self._direction_forward = True

    # -------------------------------------------------
    # GPIO setup / cleanup
    # -------------------------------------------------
    def setup(self):
        if self.h is not None:
            return

        self.h = lgpio.gpiochip_open(0)

        lgpio.gpio_claim_output(self.h, self.pin_en, 0)
        lgpio.group_claim_output(self.h, [self.pin_a, self.pin_b], [0, 0])

        self.write = lgpio.gpio_write

        # Keep booster disabled until power_on() is called
        self.write(self.h, self.pin_en, 0)
        self._set_outputs_low()

        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()

        self.logger(
            f"[DCC] Ready (ADDR={self.loco_address}, ENA={self.pin_en}, "
            f"IN1={self.pin_a}, IN2={self.pin_b})"
        )

    def cleanup(self):
        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None

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

    # -------------------------------------------------
    # Power control
    # -------------------------------------------------
    def power_on(self):
        if self.h is None:
            self.setup()
        self.write(self.h, self.pin_en, 1)
        with self._lock:
            self._track_power = True
        self.logger("[DCC] Track power ON")

    def power_off(self):
        with self._lock:
            self._track_power = False
            self._mode = "off"
            self._speed = 0
        try:
            if self.h is not None:
                lgpio.tx_wave(self.h, self.group_leader, [])
        except Exception:
            pass
        self._set_outputs_low()
        if self.h is not None:
            self.write(self.h, self.pin_en, 0)
        self.logger("[DCC] Track power OFF")

    def _set_outputs_low(self):
        if self.h is None:
            return
        lgpio.group_write(self.h, self.group_leader, 0b00, 0b11)

    # -------------------------------------------------
    # Packet helpers
    # -------------------------------------------------
    @staticmethod
    def xor_checksum(bytes_list):
        csum = 0
        for b in bytes_list:
            csum ^= b
        return csum

    def build_packet(self, address, data_bytes):
        packet = [address] + list(data_bytes)
        packet.append(self.xor_checksum(packet))
        return packet

    @staticmethod
    def byte_to_bits(byte):
        return [(byte >> i) & 1 for i in range(7, -1, -1)]

    def build_bitstream(self, packet):
        bits = [1] * 14  # preamble

        for byte in packet:
            bits.append(0)  # start bit before each byte
            bits.extend(self.byte_to_bits(byte))

        bits.append(1)  # end bit
        return bits

    # -------------------------------------------------
    # DCC instruction bytes
    # -------------------------------------------------
    @staticmethod
    def _speed_28_step_data(step, forward=True):
        """
        Practical 28-step speed packet encoding.
        step: 0..28
        """
        step = max(0, min(28, step))

        if step == 0:
            return 0b01000000  # stop

        # map 1..28 into DCC 28-step encoded value
        enc = step + 3
        c_bit = enc & 0x01
        s_nibble = (enc >> 1) & 0x0F
        direction_bit = 0x20 if forward else 0x00

        return 0x40 | direction_bit | (c_bit << 4) | s_nibble

    @staticmethod
    def _map_raw_speed_to_step28(speed):
        speed = max(0, min(126, int(speed)))
        if speed == 0:
            return 0
        return max(1, min(28, int(round(speed * 28 / 126))))

    def build_idle_packet(self):
        return self.build_packet(0xFF, [0x00])

    def build_stop_packet(self):
        data = self._speed_28_step_data(0, True)
        return self.build_packet(self.loco_address, [data])

    def build_speed_packet(self, speed, forward=True):
        step28 = self._map_raw_speed_to_step28(speed)
        data = self._speed_28_step_data(step28, forward)
        return self.build_packet(self.loco_address, [data])

    # -------------------------------------------------
    # Wave helpers
    # -------------------------------------------------
    def _dcc_bit_pulses(self, us):
        # group order is [pin_a, pin_b]
        # first half-cycle: IN1=1, IN2=0
        # second half-cycle: IN1=0, IN2=1
        return [
            self.Pulse(0b01, 0b11, us),
            self.Pulse(0b10, 0b11, us),
        ]

    def bitstream_to_pulses(self, bits):
        pulses = []
        for bit in bits:
            if bit == 1:
                pulses.extend(self._dcc_bit_pulses(self.ONE_US))
            else:
                pulses.extend(self._dcc_bit_pulses(self.ZERO_US))
        return pulses

    def packet_to_pulses(self, packet):
        bits = self.build_bitstream(packet)
        return self.bitstream_to_pulses(bits)

    def _send_pulses(self, pulses):
        if self.h is None:
            self.setup()

        while lgpio.tx_room(self.h, self.group_leader, lgpio.TX_WAVE) <= 0:
            time.sleep(0.001)

        lgpio.tx_wave(self.h, self.group_leader, pulses)

        while lgpio.tx_busy(self.h, self.group_leader, lgpio.TX_WAVE):
            time.sleep(0.001)

    def send_packet_now(self, packet, repeat=1):
        pulses = self.packet_to_pulses(packet)
        for _ in range(repeat):
            self._send_pulses(pulses)

    # -------------------------------------------------
    # Command-station scheduler
    # -------------------------------------------------
    def _scheduler_loop(self):
        idle_counter = 0

        while self._running:
            try:
                with self._lock:
                    track_power = self._track_power
                    mode = self._mode
                    speed = self._speed
                    direction_forward = self._direction_forward

                if not track_power:
                    self._set_outputs_low()
                    time.sleep(self.refresh_sec)
                    continue

                # keep ENA high whenever track power is on
                self.write(self.h, self.pin_en, 1)

                if mode == "off":
                    self._set_outputs_low()

                elif mode == "idle":
                    self.send_packet_now(self.build_idle_packet(), repeat=self.idle_repeat)

                elif mode == "stop":
                    self.send_packet_now(self.build_stop_packet(), repeat=self.packet_repeat)

                elif mode == "forward":
                    self.send_packet_now(
                        self.build_speed_packet(speed, True),
                        repeat=self.packet_repeat
                    )

                elif mode == "reverse":
                    self.send_packet_now(
                        self.build_speed_packet(speed, False),
                        repeat=self.packet_repeat
                    )

                # inject an idle packet occasionally like a command station
                idle_counter += 1
                if track_power and idle_counter >= 4:
                    self.send_packet_now(self.build_idle_packet(), repeat=1)
                    idle_counter = 0

            except Exception as e:
                self.logger(f"[DCC] Scheduler error: {e}")

            time.sleep(self.refresh_sec)

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------
    def set_address(self, address):
        self.loco_address = int(address)
        self.logger(f"[DCC] Loco address set to {self.loco_address}")

    def dcc_idle(self):
        self.power_on()
        with self._lock:
            self._mode = "idle"
            self._speed = 0
        self.logger("[DCC] idle mode set")

    def stop(self):
        self.power_on()
        with self._lock:
            self._mode = "stop"
            self._speed = 0
        self.logger("[DCC] stop mode set")

    def forward(self, speed=20):
        self.power_on()
        with self._lock:
            self._mode = "forward"
            self._direction_forward = True
            self._speed = int(speed)
        self.logger(f"[DCC] forward mode set: speed={speed}")

    def reverse(self, speed=20):
        self.power_on()
        with self._lock:
            self._mode = "reverse"
            self._direction_forward = False
            self._speed = int(speed)
        self.logger(f"[DCC] reverse mode set: speed={speed}")

    # -------------------------------------------------
    # Scope-only test
    # -------------------------------------------------
    def build_test_wave(self):
        pulses = []
        for _ in range(20):
            pulses.extend(self._dcc_bit_pulses(self.ONE_US))
        pulses.extend(self._dcc_bit_pulses(self.ZERO_US))
        return pulses

    def test_signal(self):
        self.power_on()
        self.logger("[DCC] Running tx_wave test... Ctrl+C to stop")
        try:
            while True:
                self._send_pulses(self.build_test_wave())
        except KeyboardInterrupt:
            self.logger("[DCC] Test stopped")
            self.power_off()