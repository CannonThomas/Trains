#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/select.h>

#include "piolib.h"
#include "dcc_wave.pio.h"

#define PIN_ENA 18
#define PIN_IN2 23
#define PIN_IN1 24

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100
//hello
static uint32_t txbuf[4096];
static int txlen = 0;

static uint8_t data_byte = 0x60;
static bool track_on = false;

static inline uint32_t count_from_us(uint32_t us)
{
    return us > 3 ? us - 3 : 1;
}

static void add_half(uint32_t count)
{
    if (txlen < 4096)
    {
        txbuf[txlen++] = count;
    }
}

static void add_bit(int bit, uint32_t one_count, uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    add_half(count);
    add_half(count);
}

static void add_byte(uint8_t b, uint32_t one_count, uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
    {
        add_bit((b >> i) & 1, one_count, zero_count);
    }
}

static int build_packet(uint8_t addr, uint8_t data,
                        uint32_t one_count,
                        uint32_t zero_count)
{
    uint8_t checksum = addr ^ data;

    txlen = 0;

    for (int i = 0; i < 14; i++)
    {
        add_bit(1, one_count, zero_count);
    }

    add_bit(0, one_count, zero_count);
    add_byte(addr, one_count, zero_count);

    add_bit(0, one_count, zero_count);
    add_byte(data, one_count, zero_count);

    add_bit(0, one_count, zero_count);
    add_byte(checksum, one_count, zero_count);

    add_bit(1, one_count, zero_count);

    return txlen * sizeof(uint32_t);
}

static void handle_keyboard(void)
{
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0)
    {
        return;
    }

    char c = 0;
    if (read(STDIN_FILENO, &c, 1) <= 0)
    {
        return;
    }

    if (c == 'f' || c == 'F')
    {
        data_byte = 0x63;
        track_on = true;
        printf("\nFORWARD: 03 63 60\n");
    }
    else if (c == 'r' || c == 'R')
    {
        data_byte = 0x43;
        track_on = true;
        printf("\nREVERSE: 03 43 40\n");
    }
    else if (c == 's' || c == 'S')
    {
        data_byte = 0x60;
        track_on = true;
        printf("\nSTOP PACKETS: 03 60 63\n");
    }
    else if (c == 'x' || c == 'X')
    {
        track_on = false;
        printf("\nTRACK OFF\n");
    }

    fflush(stdout);
}

int main(void)
{
    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);

    pio_sm_config_xfer(pio, sm, PIO_DIR_TO_SM, sizeof(txbuf), 1);

    uint offset = pio_add_program(pio, &dcc_wave_program);

    printf("Pi 5 RP1 PIOLib DCC test\n");
    printf("Loaded PIO program at offset %u, SM %d\n", offset, sm);
    printf("GPIO23 = IN2, GPIO24 = IN1, GPIO18 = ENA\n");
    printf("Commands: f r s x\n");

    pio_sm_clear_fifos(pio, sm);
    pio_sm_set_clkdiv(pio, sm, 125.0f);

    dcc_wave_program_init(pio, sm, offset, PIN_IN2);

    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    while (1)
    {
        handle_keyboard();

        if (track_on)
        {
            int bytes = build_packet(LOCO_ADDR, data_byte, one_count, zero_count);
            pio_sm_xfer_data(pio, sm, PIO_DIR_TO_SM, bytes, (uint8_t *)txbuf);
        }
        else
        {
            usleep(1000);
        }
    }

    return 0;
}