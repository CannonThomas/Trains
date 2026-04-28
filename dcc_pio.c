#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <sched.h>
#include <sys/mman.h>
#include <gpiod.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_EN 18
#define PIN_A  23   // L298 IN1
#define PIN_B  24   // L298 IN2

#define DCC_ONE_US   58
#define DCC_ZERO_US 116

#define LOCO_ADDR 3

#define DCC_INST_128 0x3F
#define DCC_SPEED    0x94   // forward speed 20
#define DCC_CHECKSUM (LOCO_ADDR ^ DCC_INST_128 ^ DCC_SPEED)

#define MAX_HALVES 1024

static uint32_t wave[MAX_HALVES];
static int wave_count = 0;

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
}

static inline void add_bit(int bit) {
    uint32_t count = bit ? pio_count_from_us(DCC_ONE_US)
                         : pio_count_from_us(DCC_ZERO_US);

    wave[wave_count++] = count;
    wave[wave_count++] = count;
}

static void add_byte(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        add_bit((b >> i) & 1);
    }
}

static void build_packet(void) {
    wave_count = 0;

    // Preamble
    for (int i = 0; i < 20; i++) {
        add_bit(1);
    }

    add_bit(0);
    add_byte(LOCO_ADDR);

    add_bit(0);
    add_byte(DCC_INST_128);

    add_bit(0);
    add_byte(DCC_SPEED);

    add_bit(0);
    add_byte(DCC_CHECKSUM);

    add_bit(1);
}

static void set_realtime_priority(void) {
    struct sched_param param;
    param.sched_priority = 80;
    sched_setscheduler(0, SCHED_FIFO, &param);
    mlockall(MCL_CURRENT | MCL_FUTURE);
}

int main() {
    stdio_init_all();
    set_realtime_priority();

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

    // SET pins (not side-set)
    sm_config_set_set_pins(&c, PIN_A, 2);

    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    build_packet();

    printf("Sending DCC: 03 3F 94 A8\n");

    while (1) {
        for (int i = 0; i < wave_count; i++) {
            pio_sm_put_blocking(pio, sm, wave[i]);
        }
    }

    return 0;
}