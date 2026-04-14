#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23
#define PIN_B  24

#define MAX_HALF_CYCLES 2048

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

static uint32_t databuf[MAX_HALF_CYCLES];

static void push_half_cycle(uint32_t us, int *idx) {
    if (*idx < MAX_HALF_CYCLES) {
        databuf[*idx] = us;
        (*idx)++;
    }
}

static void push_bit(int bit, int *idx) {
    uint32_t us = bit ? DCC_ONE_US : DCC_ZERO_US;
    push_half_cycle(us, idx);
    push_half_cycle(us, idx);
}

static void push_byte(uint8_t byte, int *idx) {
    for (int i = 7; i >= 0; i--) {
        push_bit((byte >> i) & 1, idx);
    }
}

static int build_dcc_packet(uint8_t address, uint8_t data) {
    int idx = 0;
    uint8_t checksum = address ^ data;

    // Preamble: at least 10 ones, use 14
    for (int i = 0; i < 14; i++) {
        push_bit(1, &idx);
    }

    // Byte 1: address
    push_bit(0, &idx);          // start bit
    push_byte(address, &idx);

    // Byte 2: data
    push_bit(0, &idx);          // start bit
    push_byte(data, &idx);

    // Byte 3: checksum
    push_bit(0, &idx);          // start bit
    push_byte(checksum, &idx);

    // Packet end bit
    push_bit(1, &idx);

    return idx;
}

int main() {
    int ret = 0;

    stdio_init_all();

    // -----------------------
    // Enable H-bridge
    // -----------------------
    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    if (!chip) {
        printf("Failed to open gpiochip0\n");
        return 1;
    }

    struct gpiod_line *en_line = gpiod_chip_get_line(chip, PIN_EN);
    if (!en_line) {
        printf("Failed to get EN line\n");
        gpiod_chip_close(chip);
        return 1;
    }

    if (gpiod_line_request_output(en_line, "dcc", 1) < 0) {
        printf("Failed to set EN high\n");
        gpiod_chip_close(chip);
        return 1;
    }

    // -----------------------
    // PIO setup
    // -----------------------
    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_A);
    pio_gpio_init(pio, PIN_B);

    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, PIN_A);

    // 125 MHz / 125 = 1 MHz -> 1 tick = 1 us
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    // -----------------------
    // Build repeated Bachmann test packet
    // -----------------------
    uint8_t address = 3;
    uint8_t data    = 104;  // same forward command you were already using

    int count = build_dcc_packet(address, data);

    printf("Loaded DCC PIO program at %u\n", offset);
    printf("Streaming packet: addr=%u data=%u checksum=%u half_cycles=%d\n",
           address, data, (address ^ data), count);

    while (1) {
        for (int i = 0; i < count; i++) {
            pio_sm_put_blocking(pio, sm, databuf[i]);
        }
    }

    // never reached in normal use
    gpiod_line_set_value(en_line, 0);
    gpiod_chip_close(chip);
    return ret;
}