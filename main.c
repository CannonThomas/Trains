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
    return us > 3 ? us - 3 : 1;
}

static void add_half(uint32_t count)
{
    if (txlen < MAX_HALVES)
        txbuf[txlen++] = count;
}

static void add_bit(int bit, uint32_t one_count, uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    // PIO half 1: GPIO23 high, GPIO24 low
    add_half(count);

    // PIO half 2: GPIO23 low, GPIO24 high
    add_half(count);
}

static void add_byte(uint8_t b, uint32_t one_count, uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
        add_bit((b >> i) & 1, one_count, zero_count);
}

static void add_packet(uint8_t addr, uint8_t data,
                       uint32_t one_count,
                       uint32_t zero_count)
{
    uint8_t checksum = addr ^ data;

    // Match old group style: 12+ ones preamble
    for (int i = 0; i < 14; i++)
        add_bit(1, one_count, zero_count);

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

    lgGpioClaimOutput(h, 0, ENB, 1);

    PIO pio = pio0;
    uint sm = pio_claim_unused_sm(pio, true);

    pio_sm_config_xfer(pio, sm, PIO_DIR_TO_SM, sizeof(txbuf), 1);

    uint offset = pio_add_program(pio, &dcc_wave_program);

    dcc_wave_program_init(pio, sm, offset, PIN_BASE);

    pio_sm_clear_fifos(pio, sm);
    pio_sm_set_enabled(pio, sm, true);

    build_repeated_forward_buffer();

    int bytes = txlen * sizeof(uint32_t);

    printf("RP1 PIO repeated DCC buffer test\n");
    printf("GPIO24 -> IN3 main track high\n");
    printf("GPIO23 -> IN4 main track low\n");
    printf("GPIO25 -> ENB\n");
    printf("Sending repeated forward packets: 03 63 60\n");
    printf("Half-cycles in buffer: %d\n", txlen);
    printf("CTRL+C to stop\n");

    while (running)
    {
        pio_sm_xfer_data(pio, sm, PIO_DIR_TO_SM, bytes, (uint8_t *)txbuf);
    }

    lgGpioWrite(h, ENB, 0);
    lgGpiochipClose(h);

    return 0;
}