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

static inline uint32_t pio_count_from_us(uint32_t us) {
    // pull + mov already consume 2 cycles before the hold loop
    if (us > 2) return us - 2;
    return 1;
}

int main() {
    stdio_init_all();

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
        printf("Failed to enable EN\n");
        gpiod_chip_close(chip);
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

    // 125 MHz / 125 = 1 MHz, so 1 PIO cycle ≈ 1 µs
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count  = pio_count_from_us(DCC_ONE_US);
    uint32_t zero_count = pio_count_from_us(DCC_ZERO_US);

    printf("Running DCC-style PIO test: one=%u zero=%u\n", one_count, zero_count);

    while (1) {
        // long preamble of 1s
        for (int i = 0; i < 200; i++) {
            pio_sm_put_blocking(pio, sm, one_count);   // 01 half
            pio_sm_put_blocking(pio, sm, one_count);   // 10 half
        }

        // a few 0s
        for (int i = 0; i < 20; i++) {
            pio_sm_put_blocking(pio, sm, zero_count);  // 01 half
            pio_sm_put_blocking(pio, sm, zero_count);  // 10 half
        }
    }

    return 0;
}