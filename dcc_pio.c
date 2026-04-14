#include <stdio.h>
#include <stdint.h>
#include <unistd.h>

#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23   // IN1
#define PIN_B  24   // IN2

#define ONE_DELAY   58
#define ZERO_DELAY  116

int main()
{
    stdio_init_all();

    // -----------------------
    // ENABLE H-BRIDGE
    // -----------------------
    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    struct gpiod_line *en_line = gpiod_chip_get_line(chip, PIN_EN);
    gpiod_line_request_output(en_line, "dcc", 1);

    // -----------------------
    // PIO SETUP
    // -----------------------
    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);

    uint offset = pio_add_program(pio, &dcc_wave_program);

    printf("Loaded DCC program at %d\n", offset);

    // init BOTH pins
    pio_gpio_init(pio, PIN_A);
    pio_gpio_init(pio, PIN_B);

    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    // IMPORTANT: sideset base pin = PIN_A (covers A + B)
    sm_config_set_sideset_pins(&c, PIN_A);

    // slow clock for correct timing
    sm_config_set_clkdiv(&c, 125.0f);  

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    printf("Starting DCC waveform...\n");

    // -----------------------
    // LOOP
    // -----------------------
    while (1)
    {
        // DCC "1" bit (short)
        pio_sm_put_blocking(pio, sm, ONE_DELAY);
        pio_sm_put_blocking(pio, sm, ONE_DELAY);

        // DCC "0" bit (long)
        pio_sm_put_blocking(pio, sm, ZERO_DELAY);
        pio_sm_put_blocking(pio, sm, ZERO_DELAY);
    }

    return 0;
}