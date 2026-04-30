// dcc_wave.pio.h
// Modified from Raspberry Pi piolib PWM header style.
// For Pi 5 RP1 PIO test: two-pin opposite-polarity DCC half-cycles.

#pragma once

#if !PICO_NO_HARDWARE
#include "hardware/pio.h"
#endif

#define dcc_wave_wrap_target 0
#define dcc_wave_wrap 5

static const uint16_t dcc_wave_program_instructions[] = {
    // Pull delay count for polarity A
    0x9080, // 0: pull noblock        side 1
    0xa027, // 1: mov  x, osr         side 1
    0x0882, // 2: jmp  x--, 2         side 1

    // Pull delay count for polarity B
    0x9000, // 3: pull noblock        side 2
    0xa027, // 4: mov  x, osr         side 2
    0x1005  // 5: jmp  x--, 5         side 2
};

#if !PICO_NO_HARDWARE
static const struct pio_program dcc_wave_program = {
    .instructions = dcc_wave_program_instructions,
    .length = 6,
    .origin = -1,
};

static inline pio_sm_config dcc_wave_program_get_default_config(uint offset)
{
    pio_sm_config c = pio_get_default_sm_config();

    sm_config_set_wrap(&c,
                       offset + dcc_wave_wrap_target,
                       offset + dcc_wave_wrap);

    // 2 side-set bits, optional=true, pindirs=false.
    // side 1 = binary 01, side 2 = binary 10.
    sm_config_set_sideset(&c, 2, true, false);

    return c;
}

static inline void dcc_wave_program_init(PIO pio, uint sm, uint offset, uint pin_base)
{
    // pin_base = GPIO23, pin_base+1 = GPIO24
    pio_gpio_init(pio, pin_base);
    pio_gpio_init(pio, pin_base + 1);

    pio_sm_set_consecutive_pindirs(pio, sm, pin_base, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    sm_config_set_sideset_pins(&c, pin_base);

    // 125 MHz / 125 = 1 MHz, so 1 PIO tick ~= 1 us.
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
}
#endif