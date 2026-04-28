#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23   // L298 IN1
#define PIN_B  24   // L298 IN2

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

#define LOCO_ADDR 3
#define SPEED_128 25
#define DIRECTION_FORWARD 1   // 1 = forward, 0 = reverse

#define MAX_HALF_CYCLES 4096
static uint32_t wavebuf[MAX_HALF_CYCLES];
static int wavecount = 0;

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
}

static void buffer_half_cycle(uint32_t us) {
    if (wavecount < MAX_HALF_CYCLES) {
        wavebuf[wavecount++] = pio_count_from_us(us);
    }
}

static void buffer_bit(int bit) {
    uint32_t us = bit ? DCC_ONE_US : DCC_ZERO_US;

    // One DCC bit = two equal half-cycles
    buffer_half_cycle(us);
    buffer_half_cycle(us);
}

static void buffer_byte(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        buffer_bit((b >> i) & 1);
    }
}

static void build_dcc_packet(uint8_t addr, bool forward, uint8_t speed) {
    uint8_t instr = 0x3F;  // 128 speed-step instruction
    uint8_t speed_byte = (forward ? 0x80 : 0x00) | (speed & 0x7F);
    uint8_t checksum = addr ^ instr ^ speed_byte;

    // Preamble
    for (int i = 0; i < 20; i++) buffer_bit(1);

    // Address
    buffer_bit(0);
    buffer_byte(addr);

    // Instruction
    buffer_bit(0);
    buffer_byte(instr);

    // Speed/direction byte
    buffer_bit(0);
    buffer_byte(speed_byte);

    // Checksum
    buffer_bit(0);
    buffer_byte(checksum);

    // End bit
    buffer_bit(1);
}

int main() {
    stdio_init_all();

    // Enable L298 ENA
    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    struct gpiod_line *en_line = gpiod_chip_get_line(chip, PIN_EN);
    gpiod_line_request_output(en_line, "dcc", 1);

    // PIO setup
    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_A);
    pio_gpio_init(pio, PIN_B);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, PIN_A);

    // 125 MHz / 125 = 1 MHz, so 1 PIO cycle ≈ 1 us
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    // Build repeated packet buffer
    wavecount = 0;

    for (int i = 0; i < 40; i++) {
        build_dcc_packet(LOCO_ADDR, DIRECTION_FORWARD, SPEED_128);
    }

    printf("DCC packet buffer built: %d half-cycles\n", wavecount);
    printf("Sending addr=%d speed=%d forward=%d\n",
           LOCO_ADDR, SPEED_128, DIRECTION_FORWARD);

    while (1) {
        for (int i = 0; i < wavecount; i++) {
            pio_sm_put_blocking(pio, sm, wavebuf[i]);
        }
    }

    return 0;
}