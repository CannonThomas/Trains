#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/select.h>
#include <string.h>
#include <stdlib.h>
#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23   // IN1
#define PIN_B  24   // IN2

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

#define LOCO_ADDR 3
#define DCC_INST_128 0x3F

#define MAX_HALVES 1024

static uint32_t wave[MAX_HALVES];
static int wave_count = 0;

// Current speed state (default = STOP forward)
static uint8_t current_speed = 0x80;

// Convert microseconds to PIO loop count
static inline uint32_t pio_count_from_us(uint32_t us) {
    if (us > 2) return us - 2;
    return 1;
}

// Add one DCC bit (2 half cycles)
static inline void add_bit(int bit) {
    uint32_t count = bit ? pio_count_from_us(DCC_ONE_US)
                         : pio_count_from_us(DCC_ZERO_US);

    wave[wave_count++] = count;
    wave[wave_count++] = count;
}

// Add byte MSB first
static void add_byte(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        add_bit((b >> i) & 1);
    }
}

// Build full NMRA DCC packet
static void build_packet(void) {
    wave_count = 0;

    uint8_t checksum = LOCO_ADDR ^ DCC_INST_128 ^ current_speed;

    // Preamble
    for (int i = 0; i < 20; i++) {
        add_bit(1);
    }

    add_bit(0);
    add_byte(LOCO_ADDR);

    add_bit(0);
    add_byte(DCC_INST_128);

    add_bit(0);
    add_byte(current_speed);

    add_bit(0);
    add_byte(checksum);

    add_bit(1);
}

// Handle commands from Python GUI
static void handle_stdin_command(void) {
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) > 0) {
        char line[64];

        if (fgets(line, sizeof(line), stdin)) {
            char dir;
            int speed;

            // STOP
            if (line[0] == 'S' || line[0] == 's') {
                current_speed = 0x80;
                printf("CMD: STOP\n");
                fflush(stdout);
                return;
            }

            if (sscanf(line, " %c %d", &dir, &speed) == 2) {
                if (speed < 2) speed = 2;
                if (speed > 127) speed = 127;

                if (dir == 'F' || dir == 'f') {
                    current_speed = 0x80 | speed;
                    printf("CMD: FORWARD %d\n", speed);
                } else if (dir == 'R' || dir == 'r') {
                    current_speed = speed;
                    printf("CMD: REVERSE %d\n", speed);
                }

                fflush(stdout);
            }
        }
    }
}

int main() {
    stdio_init_all();

    // Enable L298
    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    struct gpiod_line *en_line = gpiod_chip_get_line(chip, PIN_EN);
    gpiod_line_request_output(en_line, "dcc", 1);

    // Setup PIO
    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_A);
    pio_gpio_init(pio, PIN_B);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    // SIDE-SET controls polarity (GPIO23 + GPIO24)
    sm_config_set_sideset_pins(&c, PIN_A);

    // 1 MHz timing (1 count ≈ 1 µs)
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    printf("DCC Controller Ready\n");
    printf("Commands: F <speed>, R <speed>, S\n");

    while (1) {
        handle_stdin_command();
        build_packet();

        for (int i = 0; i < wave_count; i++) {
            pio_sm_put_blocking(pio, sm, wave[i]);
        }
    }

    return 0;
}