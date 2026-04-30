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
#define PIN_A  23   // IN2
#define PIN_B  24   // IN1

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

#define LOCO_ADDR 3

static struct gpiod_line *en_line = NULL;

// DEFAULT = STOP (lights stay on)
static uint8_t data_byte = 0x60;

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

    uint8_t checksum = LOCO_ADDR ^ data_byte;

    // PREAMBLE (continuous 1s)
    for (int i = 0; i < 20; i++)
        send_bit(pio, sm, 1, one_count, zero_count);

    // ADDRESS
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, LOCO_ADDR, one_count, zero_count);

    // DATA
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, data_byte, one_count, zero_count);

    // CHECKSUM
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, checksum, one_count, zero_count);

    // END BIT
    send_bit(pio, sm, 1, one_count, zero_count);
}

static void handle_cmd() {
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0) return;

    char line[64];
    if (!fgets(line, sizeof(line), stdin)) return;

    char dir;

    if (line[0] == 'S' || line[0] == 's') {
        data_byte = 0x60;
        printf("STOP → packet 03 60 63\n");
    }

    if (sscanf(line, " %c", &dir) == 1) {

        if (dir == 'F' || dir == 'f') {
            data_byte = 0x63;
            printf("FORWARD → packet 03 63 60\n");
        }
        else if (dir == 'R' || dir == 'r') {
            data_byte = 0x43;
            printf("REVERSE → packet 03 43 40\n");
        }
    }
}

int main() {

    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);

    // ENABLE PIN
    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    en_line = gpiod_chip_get_line(chip, PIN_EN);
    gpiod_line_request_output(en_line, "dcc_enable", 1);  // ALWAYS ON

    // PIO SETUP
    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_A);
    pio_gpio_init(pio, PIN_B);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, PIN_A);
    sm_config_set_clkdiv(&c, 125.0f); // 1us timing

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count  = pio_count_from_us(DCC_ONE_US);
    uint32_t zero_count = pio_count_from_us(DCC_ZERO_US);

    printf("DCC READY (simple packets)\n");
    printf("Commands: F, R, S\n");

    while (1) {

        handle_cmd();

        // ALWAYS sending packets (critical)
        send_packet(pio, sm, one_count, zero_count);
    }

    return 0;
}