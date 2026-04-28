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

#define MAX_HALVES 8192

static uint32_t wave[MAX_HALVES];
static int wave_count = 0;

static uint8_t speed_byte = 0x80;
static bool track_on = false;

static struct gpiod_line *en_line;

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
}

static inline void add_bit(int bit) {
    uint32_t count = bit ? pio_count_from_us(DCC_ONE_US)
                         : pio_count_from_us(DCC_ZERO_US);

    if (wave_count + 2 < MAX_HALVES) {
        wave[wave_count++] = count;
        wave[wave_count++] = count;
    }
}

static void add_byte(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        add_bit((b >> i) & 1);
    }
}

static void build_stream(void) {
    wave_count = 0;

    for (int r = 0; r < 12; r++) {

        uint8_t checksum = LOCO_ADDR ^ DCC_INST_128 ^ speed_byte;

        // PREAMBLE
        for (int i = 0; i < 20; i++) add_bit(1);

        add_bit(0); add_byte(LOCO_ADDR);
        add_bit(0); add_byte(DCC_INST_128);
        add_bit(0); add_byte(speed_byte);
        add_bit(0); add_byte(checksum);
        add_bit(1);
    }

    printf("Stream rebuilt | speed=0x%02X | halves=%d\n", speed_byte, wave_count);
    fflush(stdout);
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

static void handle_cmd(PIO pio, int sm) {
    fd_set rfds;
    struct timeval tv = {0,0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO+1, &rfds, NULL, NULL, &tv) <= 0)
        return;

    char line[64];

    if (!fgets(line, sizeof(line), stdin))
        return;

    char dir;
    int speed;

    if (line[0] == 'S') {
        speed_byte = 0x80;
        build_stream();
        track_disable(pio, sm);
        printf("STOP\n");
        return;
    }

    if (sscanf(line, " %c %d", &dir, &speed) == 2) {

        if (speed < 2) speed = 2;
        if (speed > 127) speed = 127;

        if (dir == 'F') {
            speed_byte = 0x80 | speed;
            printf("FORWARD %d\n", speed);
        }
        else if (dir == 'R') {
            speed_byte = speed;
            printf("REVERSE %d\n", speed);
        }

        build_stream();
        track_enable(pio, sm);
    }
}

int main() {

    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);

    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    en_line = gpiod_chip_get_line(chip, PIN_EN);
    gpiod_line_request_output(en_line, "dcc", 0);

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

    build_stream();

    printf("READY: F <speed>, R <speed>, S\n");

    while (1) {

        handle_cmd(pio, sm);

        if (track_on) {

            // KEEP FIFO FULL (critical)
            while (!pio_sm_is_tx_fifo_full(pio, sm)) {
                for (int i = 0; i < wave_count; i++) {
                    pio_sm_put(pio, sm, wave[i]);
                }
            }

        } else {
            usleep(1000);
        }
    }

    return 0;
}