#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
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
#define SPEED_128 25      // try 10-40 first
#define DIRECTION_FORWARD 1

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
}

static void send_bit(PIO pio, int sm, int bit) {
    uint32_t us = bit ? DCC_ONE_US : DCC_ZERO_US;
    uint32_t count = pio_count_from_us(us);

    // one DCC bit = two equal half-cycles
    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio, int sm, uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        send_bit(pio, sm, (b >> i) & 1);
    }
}

static void send_packet_128(PIO pio, int sm, uint8_t addr, bool forward, uint8_t speed) {
    if (speed > 127) speed = 127;

    uint8_t instruction = 0x3F;                 // 128-speed-step instruction
    uint8_t speed_byte = (forward ? 0x80 : 0x00) | speed;
    uint8_t checksum = addr ^ instruction ^ speed_byte;

    // Preamble: at least 10 ones, use 16
    for (int i = 0; i < 16; i++) send_bit(pio, sm, 1);

    send_bit(pio, sm, 0);
    send_byte(pio, sm, addr);

    send_bit(pio, sm, 0);
    send_byte(pio, sm, instruction);

    send_bit(pio, sm, 0);
    send_byte(pio, sm, speed_byte);

    send_bit(pio, sm, 0);
    send_byte(pio, sm, checksum);

    send_bit(pio, sm, 1);   // end bit
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

    // 125 MHz / 125 = 1 MHz, so 1 cycle ≈ 1 us
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    printf("Sending DCC 128-step packet: addr=%d speed=%d forward=%d\n",
           LOCO_ADDR, SPEED_128, DIRECTION_FORWARD);

    while (1) {
        send_packet_128(pio, sm, LOCO_ADDR, DIRECTION_FORWARD, SPEED_128);
    }

    return 0;
}