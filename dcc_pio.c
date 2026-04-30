#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/select.h>
#include <lgpio.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define GPIOCHIP 0

#define ENA 18
#define PIN_A 23   // IN2
#define PIN_B 24   // IN1

#define DCC_ONE_US   58
#define DCC_ZERO_US 100

#define LOCO_ADDR 3

static int h;
static uint8_t data_byte = 0x60; // STOP packet

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? us - 2 : 1;
}

static inline void send_bit(PIO pio, int sm, int bit,
                            uint32_t one_count,
                            uint32_t zero_count) {
    uint32_t count = bit ? one_count : zero_count;

    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio, int sm, uint8_t b,
                      uint32_t one_count,
                      uint32_t zero_count) {
    for (int i = 7; i >= 0; i--) {
        send_bit(pio, sm, (b >> i) & 1, one_count, zero_count);
    }
}

static void send_packet(PIO pio, int sm,
                        uint32_t one_count,
                        uint32_t zero_count) {
    uint8_t checksum = LOCO_ADDR ^ data_byte;

    for (int i = 0; i < 12; i++) send_bit(pio, sm, 1, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, LOCO_ADDR, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, data_byte, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, checksum, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static void handle_cmd(void) {
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0) return;

    char line[64];
    if (!fgets(line, sizeof(line), stdin)) return;

    if (line[0] == 'F' || line[0] == 'f') {
        data_byte = 0x63;
        lgGpioWrite(h, ENA, 1);
        printf("FORWARD | packet 03 63 60\n");
    }
    else if (line[0] == 'R' || line[0] == 'r') {
        data_byte = 0x43;
        lgGpioWrite(h, ENA, 1);
        printf("REVERSE | packet 03 43 40\n");
    }
    else if (line[0] == 'S' || line[0] == 's') {
        data_byte = 0x60;
        lgGpioWrite(h, ENA, 1);   // keep DCC alive, send stop packet
        printf("STOP PACKETS | packet 03 60 63 | ENA ON\n");
    }
    else if (line[0] == 'X' || line[0] == 'x') {
        data_byte = 0x60;
        lgGpioWrite(h, ENA, 0);   // emergency kill
        printf("EMERGENCY OFF | ENA OFF\n");
    }

    fflush(stdout);
}

int main() {
    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);

    h = lgGpiochipOpen(GPIOCHIP);
    if (h < 0) {
        printf("Failed to open gpiochip\n");
        return 1;
    }

    lgGpioClaimOutput(h, 0, ENA, 1); // ENA always on for DCC

    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_A); // GPIO23 / IN2
    pio_gpio_init(pio, PIN_B); // GPIO24 / IN1
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, PIN_A);
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count  = pio_count_from_us(DCC_ONE_US);
    uint32_t zero_count = pio_count_from_us(DCC_ZERO_US);

    printf("DCC PIO with verified polarity logic\n");
    printf("GPIO18=ENA, GPIO23=IN2, GPIO24=IN1\n");
    printf("Commands: F, R, S, X\n");

    while (1) {
        handle_cmd();
        send_packet(pio, sm, one_count, zero_count);
    }

    lgGpiochipClose(h);
    return 0;
}