cat > dcc_pio.c <<'EOF'
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/select.h>
#include <lgpio.h>

#include "piolib.h"
#include "dcc_wave.pio.h"

#define GPIOCHIP 0

// Your older working-ish wiring:
// GPIO18 -> ENA
// GPIO23 -> IN2
// GPIO24 -> IN1
#define ENA 18
#define PIN_A 23
#define PIN_B 24

#define DCC_ONE_US   58
#define DCC_ZERO_US 100

#define LOCO_ADDR 3

static int h = -1;
static uint8_t data_byte = 0x60; // STOP packet by default

static inline uint32_t pio_count_from_us(uint32_t us)
{
    return (us > 2) ? us - 2 : 1;
}

static inline void send_bit(PIO pio,
                            uint sm,
                            int bit,
                            uint32_t one_count,
                            uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    // PIO program alternates:
    // 1st count -> GPIO23=1 GPIO24=0
    // 2nd count -> GPIO23=0 GPIO24=1
    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio,
                      uint sm,
                      uint8_t b,
                      uint32_t one_count,
                      uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
    {
        send_bit(pio, sm, (b >> i) & 1, one_count, zero_count);
    }
}

static void send_packet(PIO pio,
                        uint sm,
                        uint32_t one_count,
                        uint32_t zero_count)
{
    uint8_t checksum = LOCO_ADDR ^ data_byte;

    // Same simple style as previous group: 12 preamble 1 bits
    for (int i = 0; i < 12; i++)
    {
        send_bit(pio, sm, 1, one_count, zero_count);
    }

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, LOCO_ADDR, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, data_byte, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, checksum, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static void handle_cmd(void)
{
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0)
    {
        return;
    }

    char line[64];

    if (!fgets(line, sizeof(line), stdin))
    {
        return;
    }

    if (line[0] == 'F' || line[0] == 'f')
    {
        data_byte = 0x63;
        lgGpioWrite(h, ENA, 1);
        printf("FORWARD | packet 03 63 60\n");
    }
    else if (line[0] == 'R' || line[0] == 'r')
    {
        data_byte = 0x43;
        lgGpioWrite(h, ENA, 1);
        printf("REVERSE | packet 03 43 40\n");
    }
    else if (line[0] == 'S' || line[0] == 's')
    {
        data_byte = 0x60;
        lgGpioWrite(h, ENA, 1);
        printf("STOP PACKETS | packet 03 60 63 | ENA ON\n");
    }
    else if (line[0] == 'X' || line[0] == 'x')
    {
        data_byte = 0x60;
        lgGpioWrite(h, ENA, 0);
        printf("EMERGENCY OFF | ENA OFF\n");
    }

    fflush(stdout);
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);

    h = lgGpiochipOpen(GPIOCHIP);

    if (h < 0)
    {
        printf("Failed to open gpiochip\n");
        return 1;
    }

    if (lgGpioClaimOutput(h, 0, ENA, 1) < 0)
    {
        printf("Failed to claim ENA GPIO%d\n", ENA);
        lgGpiochipClose(h);
        return 1;
    }

    PIO pio = pio0;

    uint sm = pio_claim_unused_sm(pio, true);
    printf("Claimed SM: %u\n", sm);

    uint offset = pio_add_program(pio, &dcc_wave_program);
    printf("Loaded PIO program at offset: %u\n", offset);

    dcc_wave_program_init(pio, sm, offset, PIN_A);

    pio_sm_clear_fifos(pio, sm);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count = pio_count_from_us(DCC_ONE_US);
    uint32_t zero_count = pio_count_from_us(DCC_ZERO_US);

    printf("DCC PIO live packet sender\n");
    printf("GPIO18=ENA, GPIO23=IN2, GPIO24=IN1\n");
    printf("Commands: F, R, S, X\n");
    printf("one_count=%u zero_count=%u\n", one_count, zero_count);

    while (1)
    {
        handle_cmd();
        send_packet(pio, sm, one_count, zero_count);
    }

    lgGpioWrite(h, ENA, 0);
    lgGpiochipClose(h);

    return 0;
}
EOF