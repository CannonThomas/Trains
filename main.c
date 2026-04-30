#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>
#include <sys/select.h>

#include "hardware/pio.h"
#include <lgpio.h>

#define GPIOCHIP 0

#define PIN_ENA 18
#define PIN_IN2 23
#define PIN_IN1 24

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static int gpio_handle = -1;
static volatile bool running = true;
static bool track_on = false;
static uint8_t data_byte = 0x60;

/*
 * Raw PIO instructions for:
 *
 * .program dcc_wave
 * .side_set 2
 *
 * pull block        side 0b01
 * mov x, osr        side 0b01
 * loop_a:
 * jmp x-- loop_a    side 0b01
 *
 * pull block        side 0b10
 * mov x, osr        side 0b10
 * loop_b:
 * jmp x-- loop_b    side 0b10
 *
 * side 0b01 = GPIO23 high, GPIO24 low
 * side 0b10 = GPIO23 low, GPIO24 high
 */
static const uint16_t dcc_wave_program_instructions[] = {
    0x88a0,
    0xa827,
    0x0842,
    0x90a0,
    0xb027,
    0x1045
};

static const struct pio_program dcc_wave_program = {
    .instructions = dcc_wave_program_instructions,
    .length = 6,
    .origin = -1
};

static void handle_sigint(int sig)
{
    (void)sig;
    running = false;
}

static uint32_t count_from_us(uint32_t us)
{
    /*
     * Each half-cycle has:
     * pull + mov + loop overhead
     * so subtract a small offset.
     */
    return us > 3 ? us - 3 : 1;
}

static void send_half(PIO pio, unsigned int sm, uint32_t count)
{
    pio_sm_put_blocking(pio, sm, count);
}

static void send_bit(PIO pio, unsigned int sm, int bit,
                     uint32_t one_count,
                     uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    // First half polarity: IN2=1 IN1=0
    send_half(pio, sm, count);

    // Second half polarity: IN2=0 IN1=1
    send_half(pio, sm, count);
}

static void send_byte(PIO pio, unsigned int sm, uint8_t b,
                      uint32_t one_count,
                      uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
    {
        send_bit(pio, sm, (b >> i) & 1, one_count, zero_count);
    }
}

static void send_packet(PIO pio, unsigned int sm,
                        uint8_t addr,
                        uint8_t data,
                        uint32_t one_count,
                        uint32_t zero_count)
{
    uint8_t checksum = addr ^ data;

    // Preamble
    for (int i = 0; i < 14; i++)
    {
        send_bit(pio, sm, 1, one_count, zero_count);
    }

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, addr, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, data, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, checksum, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static void set_track(bool on)
{
    track_on = on;

    if (gpio_handle >= 0)
    {
        lgGpioWrite(gpio_handle, PIN_ENA, on ? 1 : 0);
    }
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
        set_track(true);
        printf("\nFORWARD: 03 63 60\n");
    }
    else if (c == 'r' || c == 'R')
    {
        data_byte = 0x43;
        set_track(true);
        printf("\nREVERSE: 03 43 40\n");
    }
    else if (c == 's' || c == 'S')
    {
        data_byte = 0x60;
        set_track(true);
        printf("\nSTOP PACKETS: 03 60 63\n");
    }
    else if (c == 'x' || c == 'X')
    {
        set_track(false);
        printf("\nTRACK OFF\n");
    }
    else if (c == 'q' || c == 'Q')
    {
        running = false;
    }

    fflush(stdout);
}

int main(void)
{
    signal(SIGINT, handle_sigint);

    gpio_handle = lgGpiochipOpen(GPIOCHIP);
    if (gpio_handle < 0)
    {
        printf("Failed to open lgpio chip\n");
        return 1;
    }

    if (lgGpioClaimOutput(gpio_handle, 0, PIN_ENA, 0) < 0)
    {
        printf("Failed to claim ENA GPIO%d\n", PIN_ENA);
        return 1;
    }

    PIO pio = pio0;
    unsigned int sm = pio_claim_unused_sm(pio, true);
    unsigned int offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_IN2);
    pio_gpio_init(pio, PIN_IN1);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_IN2, 2, true);

    pio_sm_config config = pio_get_default_sm_config();

    sm_config_set_wrap(&config, offset + 0, offset + 5);
    sm_config_set_sideset(&config, 2, false, false);
    sm_config_set_sideset_pins(&config, PIN_IN2);

    // Target ~1 MHz PIO timing. Adjust after scope if needed.
    sm_config_set_clkdiv(&config, 125.0f);

    pio_sm_clear_fifos(pio, sm);
    pio_sm_init(pio, sm, offset, &config);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    printf("Pi 5 RP1 PIO DCC ready\n");
    printf("GPIO18 = ENA\n");
    printf("GPIO23 = IN2\n");
    printf("GPIO24 = IN1\n");
    printf("Commands: f r s x q\n");
    printf("Start with scope only. Type f to begin packets.\n");

    while (running)
    {
        handle_keyboard();

        if (track_on)
        {
            send_packet(pio, sm, LOCO_ADDR, data_byte, one_count, zero_count);
        }
        else
        {
            usleep(1000);
        }
    }

    set_track(false);

    if (gpio_handle >= 0)
    {
        lgGpiochipClose(gpio_handle);
    }

    printf("\nStopped.\n");
    return 0;
}