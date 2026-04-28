#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/select.h>
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
#define DCC_INST_128 0x3F

static uint8_t speed_byte = 0x80; // stop
static uint8_t func_byte  = 0x10; // F0/headlight ON
static int horn_packets = 0;

static inline uint32_t pio_count_from_us(uint32_t us) {
    return (us > 2) ? (us - 2) : 1;
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

static void send_packet3(PIO pio, int sm,
                         uint8_t b0, uint8_t b1, uint8_t b2,
                         uint32_t one_count, uint32_t zero_count) {
    for (int i = 0; i < 20; i++) send_bit(pio, sm, 1, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count); send_byte(pio, sm, b0, one_count, zero_count);
    send_bit(pio, sm, 0, one_count, zero_count); send_byte(pio, sm, b1, one_count, zero_count);
    send_bit(pio, sm, 0, one_count, zero_count); send_byte(pio, sm, b2, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static void send_packet4(PIO pio, int sm,
                         uint8_t b0, uint8_t b1, uint8_t b2, uint8_t b3,
                         uint32_t one_count, uint32_t zero_count) {
    for (int i = 0; i < 20; i++) send_bit(pio, sm, 1, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count); send_byte(pio, sm, b0, one_count, zero_count);
    send_bit(pio, sm, 0, one_count, zero_count); send_byte(pio, sm, b1, one_count, zero_count);
    send_bit(pio, sm, 0, one_count, zero_count); send_byte(pio, sm, b2, one_count, zero_count);
    send_bit(pio, sm, 0, one_count, zero_count); send_byte(pio, sm, b3, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static void send_speed_packet(PIO pio, int sm,
                              uint32_t one_count, uint32_t zero_count) {
    uint8_t checksum = LOCO_ADDR ^ DCC_INST_128 ^ speed_byte;
    send_packet4(pio, sm, LOCO_ADDR, DCC_INST_128, speed_byte, checksum,
                 one_count, zero_count);
}

static void send_function_packet(PIO pio, int sm,
                                 uint32_t one_count, uint32_t zero_count) {
    /*
      Function group 1:
      100D DDDD
      0x80 base
      bit 4 = F0/headlight
      bit 1 = F2/horn
    */
    uint8_t f = 0x80 | func_byte;

    if (horn_packets > 0) {
        f |= 0x02;        // F2 horn ON
        horn_packets--;
    }

    uint8_t checksum = LOCO_ADDR ^ f;
    send_packet3(pio, sm, LOCO_ADDR, f, checksum, one_count, zero_count);
}

static void handle_cmd(void) {
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0) return;

    char line[64];
    if (!fgets(line, sizeof(line), stdin)) return;

    char dir;
    int speed;

    if (line[0] == 'S' || line[0] == 's') {
        speed_byte = 0x80;  // DCC stop, track power stays on
        func_byte = 0x10;   // F0/headlight ON
        printf("STOP | packet 03 3F 80 BC | lights ON\n");
        fflush(stdout);
        return;
    }

    if (line[0] == 'H' || line[0] == 'h') {
        horn_packets = 80;
        printf("HORN TEST | F2 ON briefly\n");
        fflush(stdout);
        return;
    }

    if (sscanf(line, " %c %d", &dir, &speed) == 2) {
        if (speed < 2) speed = 2;
        if (speed > 127) speed = 127;

        if (dir == 'F' || dir == 'f') {
            speed_byte = 0x80 | speed;
            printf("FORWARD %d | packet %02X %02X %02X %02X\n",
                   speed, LOCO_ADDR, DCC_INST_128, speed_byte,
                   LOCO_ADDR ^ DCC_INST_128 ^ speed_byte);
        } else if (dir == 'R' || dir == 'r') {
            speed_byte = speed;
            printf("REVERSE %d | packet %02X %02X %02X %02X\n",
                   speed, LOCO_ADDR, DCC_INST_128, speed_byte,
                   LOCO_ADDR ^ DCC_INST_128 ^ speed_byte);
        }

        func_byte = 0x10; // keep lights ON
        fflush(stdout);
    }
}

int main() {
    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);

    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    if (!chip) return 1;

    struct gpiod_line *en_line = gpiod_chip_get_line(chip, PIN_EN);
    if (!en_line) return 1;

    if (gpiod_line_request_output(en_line, "dcc_enable", 1) < 0) return 1;

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

    uint32_t one_count  = pio_count_from_us(DCC_ONE_US);
    uint32_t zero_count = pio_count_from_us(DCC_ZERO_US);

    printf("Bachmann GP30 #6944 DCC ready\n");
    printf("Commands: F <speed>, R <speed>, S, H\n");

    while (1) {
        handle_cmd();

        // send speed often, function packets regularly so lights stay on
        send_speed_packet(pio, sm, one_count, zero_count);
        send_function_packet(pio, sm, one_count, zero_count);
    }

    return 0;
}