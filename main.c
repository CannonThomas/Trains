#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>
#include <lgpio.h>

#include "piolib.h"
#include "dcc_wave.pio.h"

#define GPIOCHIP 0

// L298 main-track enable
#define ENB 25

// PIO output pins must be consecutive.
// GPIO23 = PIO bit0
// GPIO24 = PIO bit1
#define PIN_BASE 23

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

/*
 * Bigger buffer = fewer Linux refill gaps.
 * One DCC packet has 42 bits = 84 half-cycles.
 * 512 packets = 43008 half-cycles.
 */
#define PACKET_REPEATS 512
#define MAX_HALVES 65536

static int h = -1;
static volatile bool running = true;

static uint32_t txbuf[MAX_HALVES];
static int txlen = 0;

static uint32_t count_from_us(uint32_t us)
{
    /*
     * PIO timing estimate:
     * Each half-cycle includes pull/mov/set/jmp overhead.
     * Start at us - 4, tune by scope later.
     */
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

    /*
     * PIO program alternates:
     * first pulled count  -> set pins, 1 -> GPIO23=1 GPIO24=0
     * second pulled count -> set pins, 2 -> GPIO23=0 GPIO24=1
     */
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

static void add_packet(uint8_t addr,
                       uint8_t data,
                       uint32_t one_count,
                       uint32_t zero_count)
{
    uint8_t checksum = addr ^ data;

    // Preamble: 14 logic-1 bits
    for (int i = 0; i < 14; i++)
    {
        add_bit(1, one_count, zero_count);
    }

    // Start + address
    add_bit(0, one_count, zero_count);
    add_byte(addr, one_count, zero_count);

    // Start + data
    add_bit(0, one_count, zero_count);
    add_byte(data, one_count, zero_count);

    // Start + checksum
    add_bit(0, one_count, zero_count);
    add_byte(checksum, one_count, zero_count);

    // End bit
    add_bit(1, one_count, zero_count);
}

static void add_idle_packet(uint32_t one_count, uint32_t zero_count)
{
    // DCC idle packet: FF 00 FF
    add_packet(0xFF, 0x00, one_count, zero_count);
}

static void build_repeated_forward_buffer(void)
{
    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    txlen = 0;

    for (int i = 0; i < PACKET_REPEATS; i++)
    {
        /*
         * Repeating forward command:
         * addr=03 data=63 checksum=60
         */
        add_packet(LOCO_ADDR, 0x63, one_count, zero_count);

        /*
         * Optional idle between commands.
         * This keeps DCC alive and gives decoder valid packets.
         * Comment this out if you want only forward packets.
         */
        add_idle_packet(one_count, zero_count);
    }

    printf("one_count=%u zero_count=%u\n", one_count, zero_count);
}

static void handle_sigint(int sig)
{
    (void)sig;
    running = false;
}

static void dcc_wave_init(PIO pio, uint sm, uint offset, uint pin_base)
{
    pio_gpio_init(pio, pin_base);
    pio_gpio_init(pio, pin_base + 1);

    pio_sm_set_consecutive_pindirs(pio, sm, pin_base, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    // Our PIO uses "set pins, 1" and "set pins, 2"
    sm_config_set_set_pins(&c, pin_base, 2);

    // 125 MHz / 125 = about 1 MHz, 1 cycle ~= 1 us
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
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

    dcc_wave_init(pio, sm, offset, PIN_BASE);

    pio_sm_clear_fifos(pio, sm);

    build_repeated_forward_buffer();

    int bytes = txlen * sizeof(uint32_t);

    /*
     * Larger transfer burst.
     * This should reduce the visible gap compared to small/manual FIFO feeds.
     */
    pio_sm_config_xfer(pio, sm, PIO_DIR_TO_SM, bytes, 4);

    pio_sm_set_enabled(pio, sm, true);

    printf("RP1 PIO repeated DCC buffer test\n");
    printf("GPIO23 -> PIO bit0 / IN4\n");
    printf("GPIO24 -> PIO bit1 / IN3\n");
    printf("GPIO25 -> ENB\n");
    printf("Sending repeated forward + idle packets\n");
    printf("Forward packet: 03 63 60\n");
    printf("Idle packet:    FF 00 FF\n");
    printf("Half-cycles in buffer: %d\n", txlen);
    printf("Bytes transferred each loop: %d\n", bytes);
    printf("CTRL+C to stop\n");

    while (running)
    {
        int ret = pio_sm_xfer_data(pio,
                                   sm,
                                   PIO_DIR_TO_SM,
                                   bytes,
                                   (uint8_t *)txbuf);

        if (ret)
        {
            printf("pio_sm_xfer_data error: %d\n", ret);
            break;
        }
    }

    lgGpioWrite(h, ENB, 0);
    lgGpiochipClose(h);

    printf("\nStopped.\n");
    return 0;
}