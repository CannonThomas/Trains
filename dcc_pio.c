#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "genseq.pio.h"

#define PIN_EN   18
#define PIN_A    23

#define DATA_WORDS 1024

#define ONE_US   58
#define ZERO_US  116

static uint32_t databuf[DATA_WORDS];

static int build_test_stream(void)
{
    int idx = 0;

    // Preamble (1 bits)
    for (int i = 0; i < 200 && idx < DATA_WORDS; i++) {
        databuf[idx++] = ONE_US;
    }

    // Some 0 bits
    for (int i = 0; i < 40 && idx < DATA_WORDS; i++) {
        databuf[idx++] = ZERO_US;
    }

    return idx;
}

int main()
{
    bool use_dma = true;
    int ret = 0;

    stdio_init_all();

    // -----------------------
    // ENABLE H-BRIDGE (Linux GPIO)
    // -----------------------
    struct gpiod_chip *chip;
    struct gpiod_line *en_line;

    chip = gpiod_chip_open("/dev/gpiochip0");
    en_line = gpiod_chip_get_line(chip, PIN_EN);

    gpiod_line_request_output(en_line, "dcc", 1);

    // -----------------------
    // PIO SETUP
    // -----------------------
    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &genseq_program);

    uint gpio = PIN_A;

    printf("Loaded program at %d, using sm %d, gpio %d\n", offset, sm, gpio);

    pio_sm_config_xfer(pio, sm, PIO_DIR_FROM_SM, 256, 1);

    pio_gpio_init(pio, gpio);
    pio_sm_set_consecutive_pindirs(pio, sm, gpio, 1, true);

    pio_sm_config c = genseq_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, gpio);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    int count = build_test_stream();

    printf("Streaming %d timing words\n", count);

    // -----------------------
    // MAIN LOOP
    // -----------------------
    while (1) {
        pio_sm_put_blocking(pio, sm, 0);

        if (use_dma) {
            ret = pio_sm_xfer_data(
                pio,
                sm,
                PIO_DIR_FROM_SM,
                count * sizeof(databuf[0]),
                databuf
            );
            if (ret) {
                printf("DMA error %d\n", ret);
                break;
            }
        } else {
            for (int i = 0; i < count; i++) {
                pio_sm_put_blocking(pio, sm, databuf[i]);
            }
        }

        sleep_ms(5);
    }

    // cleanup
    gpiod_line_set_value(en_line, 0);
    gpiod_chip_close(chip);

    return ret;
}