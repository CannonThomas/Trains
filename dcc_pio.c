#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/select.h>
#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23
#define PIN_B  24

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

#define LOCO_ADDR 3
#define DCC_INST_128 0x3F

#define DEFAULT_SPEED 60

static struct gpiod_line *en_line = NULL;

static uint8_t speed_byte = 0x80;   // stop
static bool track_on = false;

static char current_dir = 'S';
static char pending_dir = 'S';
static int pending_speed = DEFAULT_SPEED;
static int transition_stop_packets = 0;

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
}

static inline void send_bit(PIO pio, int sm, int bit,
                            uint32_t one_count,
                            uint32_t zero_count) {
    uint32_t count = bit ? one_count : zero_count;

    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio, int sm, uint8_t b,
                      uint32_t one_count,
                      uint32_t zero_count) {
    for (int i = 7; i >= 0; i--) {
        send_bit(pio, sm, (b >> i) & 1, one_count, zero_count);
    }
}

static void send_packet(PIO pio, int sm,
                        uint32_t one_count,
                        uint32_t zero_count) {
    uint8_t checksum = LOCO_ADDR ^ DCC_INST_128 ^ speed_byte;

    for (int i = 0; i < 20; i++) {
        send_bit(pio, sm, 1, one_count, zero_count);
    }

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, LOCO_ADDR, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, DCC_INST_128, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, speed_byte, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, checksum, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static uint8_t make_speed_byte(char dir, int speed) {
    if (speed < 2) speed = 2;
    if (speed > 127) speed = 127;

    if (dir == 'F') {
        return 0x80 | speed;
    }

    if (dir == 'R') {
        return speed;
    }

    return 0x80;
}

static void track_enable(PIO pio, int sm) {
    gpiod_line_set_value(en_line, 1);
    pio_sm_set_enabled(pio, sm, true);
    track_on = true;
}

static void track_disable(PIO pio, int sm) {
    gpiod_line_set_value(en_line, 0);
    pio_sm_set_enabled(pio, sm, false);
    track_on = false;
}

static void print_packet(const char *label) {
    uint8_t checksum = LOCO_ADDR ^ DCC_INST_128 ^ speed_byte;

    printf("%s | packet %02X %02X %02X %02X\n",
           label,
           LOCO_ADDR,
           DCC_INST_128,
           speed_byte,
           checksum);
    fflush(stdout);
}

static void handle_cmd(PIO pio, int sm) {
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0) {
        return;
    }

    char line[64];
    if (!fgets(line, sizeof(line), stdin)) {
        return;
    }

    char dir;
    int speed;

    if (line[0] == 'S' || line[0] == 's') {
        speed_byte = 0x80;
        current_dir = 'S';
        pending_dir = 'S';
        transition_stop_packets = 0;

        track_disable(pio, sm);
        print_packet("STOP | ENA OFF | PIO OFF");
        return;
    }

    if (sscanf(line, " %c %d", &dir, &speed) == 2) {
        if (speed < 2) speed = 2;
        if (speed > 127) speed = 127;

        if (dir == 'f') dir = 'F';
        if (dir == 'r') dir = 'R';

        if (dir != 'F' && dir != 'R') {
            return;
        }

        /*
          If changing from F to R or R to F while already running:
          1. Keep track ON
          2. Send repeated stop packets first
          3. Then switch to requested direction
        */
        if (track_on &&
            current_dir != 'S' &&
            current_dir != dir) {

            speed_byte = 0x80;              // DCC stop packet
            pending_dir = dir;
            pending_speed = speed;
            transition_stop_packets = 40;   // increase to 80 if still flaky

            track_enable(pio, sm);

            printf("TRANSITION %c -> STOP BURST -> %c %d\n",
                   current_dir,
                   pending_dir,
                   pending_speed);
            print_packet("STOP BURST");
            return;
        }

        speed_byte = make_speed_byte(dir, speed);
        current_dir = dir;
        pending_dir = 'S';
        transition_stop_packets = 0;

        track_enable(pio, sm);

        if (dir == 'F') {
            printf("FORWARD %d\n", speed);
        } else {
            printf("REVERSE %d\n", speed);
        }

        print_packet("RUN");
    }
}

int main() {
    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);

    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    if (!chip) {
        printf("Failed to open gpiochip0\n");
        return 1;
    }

    en_line = gpiod_chip_get_line(chip, PIN_EN);
    if (!en_line) {
        printf("Failed to get EN line\n");
        return 1;
    }

    if (gpiod_line_request_output(en_line, "dcc_enable", 0) < 0) {
        printf("Failed to request EN line\n");
        return 1;
    }

    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_A);
    pio_gpio_init(pio, PIN_B);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, PIN_A);
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, false);

    uint32_t one_count  = pio_count_from_us(DCC_ONE_US);
    uint32_t zero_count = pio_count_from_us(DCC_ZERO_US);

    printf("DCC ready with direction-change stop burst\n");
    printf("Commands: F <speed>, R <speed>, S\n");

    while (1) {
        handle_cmd(pio, sm);

        if (track_on) {
            send_packet(pio, sm, one_count, zero_count);

            if (transition_stop_packets > 0) {
                transition_stop_packets--;

                if (transition_stop_packets == 0 && pending_dir != 'S') {
                    speed_byte = make_speed_byte(pending_dir, pending_speed);
                    current_dir = pending_dir;
                    pending_dir = 'S';

                    if (current_dir == 'F') {
                        printf("NOW FORWARD %d\n", pending_speed);
                    } else {
                        printf("NOW REVERSE %d\n", pending_speed);
                    }

                    print_packet("RUN AFTER STOP BURST");
                }
            }
        } else {
            usleep(1000);
        }
    }

    return 0;
}