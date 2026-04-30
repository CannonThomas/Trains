#pragma once
#include "piolib.h"

// PIO program:
// pulls delay count
// outputs opposite polarity each loop

static const uint16_t dcc_wave_program_instructions[] = {
    0x9080, // pull noblock    side 0
    0xa027, // mov x, osr
    0x6001, // out pins, 2     side 1   <-- flip polarity
    0x0001, // jmp x--, 2
    0x6002, // out pins, 2     side 2   <-- opposite polarity
    0x0003  // jmp x--, 4
};

static const struct pio_program dcc_wave_program = {
    .instructions = dcc_wave_program_instructions,
    .length = 6,
    .origin = -1,
};

static inline pio_sm_config dcc_wave_program_get_default_config(uint offset)
{
    pio_sm_config c = pio_get_default_sm_config();

    sm_config_set_wrap(&c, offset + 0, offset + 5);

    // 2-bit sideset → controls 2 pins
    sm_config_set_sideset(&c, 2, true, false);

    return c;
}

static inline void dcc_wave_program_init(PIO pio, uint sm, uint offset, uint pin_base)
{
    pio_gpio_init(pio, pin_base);
    pio_gpio_init(pio, pin_base + 1);

    pio_sm_set_consecutive_pindirs(pio, sm, pin_base, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    sm_config_set_sideset_pins(&c, pin_base);

    // 1 MHz timing (1us resolution)
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
}