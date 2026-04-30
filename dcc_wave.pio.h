// dcc_wave.pio.h
// Pi 5 RP1 PIO: two-pin opposite-polarity DCC half-cycle generator.
// Uses SET PINS instead of sideset.

#pragma once

#include "piolib.h"

#define dcc_wave_wrap_target 0
#define dcc_wave_wrap 7

static const uint16_t dcc_wave_program_instructions[] = {
    0x80a0, // 0: pull block
    0xa027, // 1: mov  x, osr
    0xe001, // 2: set  pins, 1   -> GPIO23=1 GPIO24=0
    0x0043, // 3: jmp  x--, 3

    0x80a0, // 4: pull block
    0xa027, // 5: mov  x, osr
    0xe002, // 6: set  pins, 2   -> GPIO23=0 GPIO24=1
    0x0047  // 7: jmp  x--, 7
};

static const struct pio_program dcc_wave_program = {
    .instructions = dcc_wave_program_instructions,
    .length = 8,
    .origin = -1,
};

static inline pio_sm_config dcc_wave_program_get_default_config(uint offset)
{
    pio_sm_config c = pio_get_default_sm_config();

    sm_config_set_wrap(&c,
                       offset + dcc_wave_wrap_target,
                       offset + dcc_wave_wrap);

    return c;
}

static inline void dcc_wave_program_init(PIO pio, uint sm, uint offset, uint pin_base)
{
    // pin_base = GPIO23, pin_base+1 = GPIO24
    pio_gpio_init(pio, pin_base);
    pio_gpio_init(pio, pin_base + 1);

    pio_sm_set_consecutive_pindirs(pio, sm, pin_base, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    // SET PINS controls GPIO23/GPIO24
    sm_config_set_set_pins(&c, pin_base, 2);

    // 125 MHz / 125 = 1 MHz, so delay loop is roughly microsecond scale.
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
}