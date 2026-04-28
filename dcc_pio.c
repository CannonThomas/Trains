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

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

#define LOCO_ADDR 3
#define DCC_DATA  104   // original forward command

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
}

static void send_bit(PIO pio, int sm, int bit) {
    uint32_t us = bit ? DCC_ONE_US : DCC_ZERO_US;
    uint32_t count = pio_count_from_us(us);

    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio, int sm, uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        send_bit(pio, sm, (b >> i) & 1);
    }
}

static void send_packet(PIO pio, int sm) {
    uint8_t checksum = LOCO_ADDR ^ DCC_DATA;

    // Preamble
    for (int i = 0; i < 20; i++) send_bit(pio, sm, 1);

    // Address
    send_bit(pio, sm, 0);
    send_byte(pio, sm, LOCO_ADDR);

    // Data
    send_bit(pio, sm, 0);
    send_byte(pio, sm, DCC_DATA);

    // Checksum
    send_bit(pio, sm, 0);
    send_byte(pio, sm, checksum);

    // End bit
    send_bit(pio, sm, 1);
}

int main() {
    stdio_init_all();

    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    struct gpiod_line *en_line = gpiod_chip_get_line(chip, PIN_EN);
    gpiod_line_request_output(en_line, "dcc", 1);

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
    pio_sm_set_enabled(pio, sm, true);

    printf("Sending simple DCC packet: addr=%d data=%d checksum=%d\n",
           LOCO_ADDR, DCC_DATA, LOCO_ADDR ^ DCC_DATA);

    while (1) {
        send_packet(pio, sm);
    }

    return 0;
}