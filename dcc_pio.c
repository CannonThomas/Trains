#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
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
#define DCC_DATA  104   // 0x68 forward command
#define DCC_CHECKSUM (LOCO_ADDR ^ DCC_DATA)

static inline uint32_t pio_count_from_us(uint32_t us) {
    if (us > 2) return us - 2;
    return 1;
}

static inline void send_bit(PIO pio, int sm, int bit,
                            uint32_t one_count, uint32_t zero_count) {
    uint32_t count = bit ? one_count : zero_count;

    // One DCC bit = two equal half-cycles
    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio, int sm, uint8_t b,
                      uint32_t one_count, uint32_t zero_count) {
    for (int i = 7; i >= 0; i--) {
        send_bit(pio, sm, (b >> i) & 1, one_count, zero_count);
    }
}

static void send_dcc_packet(PIO pio, int sm,
                            uint32_t one_count, uint32_t zero_count) {
    // Long preamble for stable decoder sync
    for (int i = 0; i < 200; i++) {
        send_bit(pio, sm, 1, one_count, zero_count);
    }

    // Start bit + address byte
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, LOCO_ADDR, one_count, zero_count);

    // Start bit + command byte
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, DCC_DATA, one_count, zero_count);

    // Start bit + checksum byte
    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, DCC_CHECKSUM, one_count, zero_count);

    // End bit
    send_bit(pio, sm, 1, one_count, zero_count);
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

    printf("Sending DCC packet:\n");
    printf("Address: %d\n", LOCO_ADDR);
    printf("Command: %d / 0x%02X\n", DCC_DATA, DCC_DATA);
    printf("Checksum: %d / 0x%02X\n", DCC_CHECKSUM, DCC_CHECKSUM);
    printf("one_count=%u zero_count=%u\n", one_count, zero_count);

    while (1) {
        send_dcc_packet(pio, sm, one_count, zero_count);
    }

    return 0;
}