#include <stdio.h>
#include <stdint.h>
#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23
#define PIN_B  24

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

// IDLE packet: FF 00 FF
#define B0 0xFF
#define B1 0x00
#define B2 0xFF

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

static void send_idle(PIO pio, int sm,
                      uint32_t one_count,
                      uint32_t zero_count) {

    // Preamble
    for (int i = 0; i < 20; i++) {
        send_bit(pio, sm, 1, one_count, zero_count);
    }

    // FF
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, B0, one_count, zero_count);

    // 00
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, B1, one_count, zero_count);

    // FF
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, B2, one_count, zero_count);

    // End
    send_bit(pio, sm, 1, one_count, zero_count);
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

    uint32_t one_count  = pio_count_from_us(DCC_ONE_US);
    uint32_t zero_count = pio_count_from_us(DCC_ZERO_US);

    printf("Sending DCC IDLE packet ONLY\n");

    while (1) {
        send_idle(pio, sm, one_count, zero_count);
    }

    return 0;
}