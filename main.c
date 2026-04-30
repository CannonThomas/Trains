#include <stdio.h>
#include <stdint.h>
#include <unistd.h>

#include <pio.h>
#include "dcc_wave.pio.h"

#define PIN_IN2 23
#define PIN_IN1 24
#define PIN_ENA 18

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static inline uint32_t count_from_us(uint32_t us)
{
    return us > 2 ? us - 2 : 1;
}

static void send_bit(PIO pio, int sm, int bit,
                     uint32_t one_count,
                     uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

int main()
{
    printf("Starting Pi5 PIO DCC test\n");

    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);

    uint offset = pio_add_program(pio, &dcc_wave_program);

    // Init pins
    pio_gpio_init(pio, PIN_IN2);
    pio_gpio_init(pio, PIN_IN1);

    pio_sm_set_consecutive_pindirs(pio, sm, PIN_IN2, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    sm_config_set_sideset_pins(&c, PIN_IN2);

    // 1 MHz clock → 1us per cycle
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    // Enable L298
    gpio_set_function(PIN_ENA, GPIO_FUNC_SIO);
    gpio_set_dir(PIN_ENA, GPIO_OUT);
    gpio_put(PIN_ENA, 1);

    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    while (1)
    {
        // Send repeating 1 bits → should show clean polarity flip
        send_bit(pio, sm, 1, one_count, zero_count);
    }

    return 0;
}