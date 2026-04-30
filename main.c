#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>
#include <lgpio.h>

#include "piolib.h"
#include "dcc_wave.pio.h"

#define GPIOCHIP 0

#define ENB 25

#define PIN_BASE 23
#define GPIO_IN4 23
#define GPIO_IN3 24

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

#define PACKET_REPEATS 32
#define MAX_HALVES 4096

static int h = -1;
static volatile bool running = true;

static uint32_t txbuf[MAX_HALVES];
static int txlen = 0;

static uint32_t count_from_us(uint32_t us)
{
    // PIO loop has overhead, so subtract a little.
    return us > 4 ? us - 4 : 1;
}

static void add_half(uint32_t count)
{
    if (txlen < MAX_HALVES)
    {
        txbuf[txlen++] = count;
    }
}

static void add_bit(int bit, uint32_t one_count, uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    // First half: GPIO23=1 GPIO24=0
    add_half(count);

    // Second half: GPIO23=0 GPIO24=1
    add_half(count);
}

static void add_byte(uint8_t b, uint32_t one_count, uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
    {
        add_bit((b >> i) & 1, one_count, zero_count);
    }
}

static void add_packet(uint8_t addr, uint8_t data,
                       uint32_t one_count,
                       uint32_t zero_count)
{
    uint8_t checksum = addr ^ data;

    // Old group style: 12+ preamble ones
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
}

static void build_repeated_forward_buffer(void)
{
    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    txlen = 0;

    for (int i = 0; i < PACKET_REPEATS; i++)
    {
        // Forward packet: 03 63 60
        add_packet(LOCO_ADDR, 0x63, one_count, zero_count);
    }
}

static void handle_sigint(int sig)
{
    (void)sig;
    running = false;
}

int main(void)
{
    signal(SIGINT, handle_sigint);

    h = lgGpiochipOpen(GPIOCHIP);
    if (h < 0)
    {
        printf("Failed to open lgpio chip\n");
        return 1;
    }

    if (lgGpioClaimOutput(h, 0, ENB, 1) < 0)
    {
        printf("Failed to claim ENB GPIO%d\n", ENB);
        return 1;
    }

    PIO pio = pio0;
    uint sm = pio_claim_unused_sm(pio, true);
    printf("Claimed SM: %u\n", sm);

    uint offset = pio_add_program(pio, &dcc_wave_program);
    printf("Loaded PIO program at offset: %u\n", offset);

    dcc_wave_program_init(pio, sm, offset, PIN_BASE);

    pio_sm_clear_fifos(pio, sm);
    pio_sm_set_enabled(pio, sm, true);

    build_repeated_forward_buffer();

    printf("RP1 PIO repeated DCC buffer test\n");
    printf("GPIO23 -> first PIO pin\n");
    printf("GPIO24 -> second PIO pin\n");
    printf("GPIO25 -> ENB\n");
    printf("Sending repeated forward packets: 03 63 60\n");
    printf("Half-cycles in buffer: %d\n", txlen);
    printf("CTRL+C to stop\n");

    while (running)
    {
        // Safer than pio_sm_xfer_data while debugging.
        for (int i = 0; i < txlen && running; i++)
        {
            pio_sm_put_blocking(pio, sm, txbuf[i]);
        }
    }

    lgGpioWrite(h, ENB, 0);
    lgGpiochipClose(h);

    return 0;
}