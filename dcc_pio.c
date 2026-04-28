#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23
#define PIN_B  24

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

#define LOCO_ADDR 3
#define DCC_DATA  104

#define MAX_HALVES 65536
#define PACKET_REPEATS 80

static uint32_t wavebuf[MAX_HALVES];
static int wavecount = 0;

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
}

static void add_bit(int bit) {
    uint32_t count = pio_count_from_us(bit ? DCC_ONE_US : DCC_ZERO_US);
    wavebuf[wavecount++] = count;
    wavebuf[wavecount++] = count;
}

static void add_byte(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        add_bit((b >> i) & 1);
    }
}

static void add_packet(void) {
    uint8_t checksum = LOCO_ADDR ^ DCC_DATA;

    for (int i = 0; i < 200; i++) add_bit(1);

    add_bit(0);
    add_byte(LOCO_ADDR);

    add_bit(0);
    add_byte(DCC_DATA);

    add_bit(0);
    add_byte(checksum);

    add_bit(1);
}

int main() {
    stdio_init_all();

    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    if (!chip) return 1;

    struct gpiod_line *en_line = gpiod_chip_get_line(chip, PIN_EN);
    if (!en_line) return 1;

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

    wavecount = 0;
    for (int i = 0; i < PACKET_REPEATS; i++) {
        add_packet();
    }

    printf("Streaming DCC buffer: addr=%d data=%d checksum=%d halves=%d\n",
           LOCO_ADDR, DCC_DATA, LOCO_ADDR ^ DCC_DATA, wavecount);

    while (1) {
        for (int i = 0; i < wavecount; i++) {
            pio_sm_put_blocking(pio, sm, wavebuf[i]);
        }
    }

    return 0;
}