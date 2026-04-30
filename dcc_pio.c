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

static struct gpiod_line *en_line = NULL;
static uint8_t speed_byte = 0x80;
static bool track_on = false;

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

    for (int i = 0; i < 20; i++) send_bit(pio, sm, 1, one_count, zero_count);

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
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0) return;

    char line[64];
    if (!fgets(line, sizeof(line), stdin)) return;

    char dir;
    int speed;

    if (line[0] == 'S' || line[0] == 's') {
        speed_byte = 0x80;
        track_disable(pio, sm);
        printf("STOP | ENA OFF | PIO OFF\n");
        fflush(stdout);
        return;
    }

    if (sscanf(line, " %c %d", &dir, &speed) == 2) {

        if (speed < 2) speed = 2;
        if (speed > 127) speed = 127;

        if (dir == 'F' || dir == 'f') {
            speed_byte = 0x80 | speed;
            printf("FORWARD %d\n", speed);
            track_enable(pio, sm);
        }
        else if (dir == 'R' || dir == 'r') {
            speed_byte = speed;
            printf("REVERSE %d\n", speed);
            track_enable(pio, sm);
        }

        fflush(stdout);
    }
}

int main() {

    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);

    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    en_line = gpiod_chip_get_line(chip, PIN_EN);
    gpiod_line_request_output(en_line, "dcc_enable", 0);

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

    printf("DCC READY (128-step version)\n");

    while (1) {
        handle_cmd(pio, sm);

        if (track_on) {
            send_packet(pio, sm, one_count, zero_count);
        } else {
            usleep(1000);
        }
    }

    return 0;
}