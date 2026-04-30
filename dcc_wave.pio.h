#pragma once
#include "piolib.h"

static const uint16_t dcc_wave_program_instructions[] = {
    0x88a0,
    0xa827,
    0x0842,
    0x90a0,
    0xb027,
    0x1045
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
    sm_config_set_sideset(&c, 2, false, false);
    return c;
}

static inline void dcc_wave_program_init(PIO pio, uint sm, uint offset, uint pin_base)
{
    pio_gpio_init(pio, pin_base);
    pio_gpio_init(pio, pin_base + 1);
    pio_sm_set_consecutive_pindirs(pio, sm, pin_base, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, pin_base);

    // 125 MHz / 125 = 1 MHz -> 1 cycle ≈ 1 us
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
}