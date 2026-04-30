#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>
#include <sys/select.h>
#include <lgpio.h>

#include "piolib.h"
#include "dcc_wave.pio.h"

#define GPIOCHIP 0

#define ENB 25

// PIO must use consecutive pins
#define PIN_BASE 23
#define IN4_GPIO 23
#define IN3_GPIO 24

#define LOCO_ADDR 3
#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static int h = -1;
static volatile bool running = true;
static bool track_on = false;
static uint8_t data_byte = 0x60;

static uint32_t count_from_us(uint32_t us)
{
    return us > 3 ? us - 3 : 1;
}

static void set_track(bool on)
{
    track_on = on;
    lgGpioWrite(h, ENB, on ? 1 : 0);
}

static void send_bit(PIO pio, uint sm, int bit, uint32_t one_count, uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    // First half: GPIO23 high / GPIO24 low
    pio_sm_put_blocking(pio, sm, count);

    // Second half: GPIO23 low / GPIO24 high
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio, uint sm, uint8_t b, uint32_t one_count, uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
        send_bit(pio, sm, (b >> i) & 1, one_count, zero_count);
}

static void send_packet(PIO pio, uint sm, uint8_t addr, uint8_t data,
                        uint32_t one_count, uint32_t zero_count)
{
    uint8_t checksum = addr ^ data;

    for (int i = 0; i < 14; i++)
        send_bit(pio, sm, 1, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, addr, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, data, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, checksum, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static void handle_keyboard(void)
{
    fd_set rfds;
    struct timeval tv = {0, 0};

    FD_ZERO(&rfds);
    FD_SET(STDIN_FILENO, &rfds);

    if (select(STDIN_FILENO + 1, &rfds, NULL, NULL, &tv) <= 0)
        return;

    char c;
    if (read(STDIN_FILENO, &c, 1) <= 0)
        return;

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
        printf("\nSTOP: 03 60 63\n");
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
    signal(SIGINT, SIG_DFL);

    h = lgGpiochipOpen(GPIOCHIP);
    if (h < 0)
    {
        printf("Failed to open lgpio chip\n");
        return 1;
    }

    lgGpioClaimOutput(h, 0, ENB, 0);

    PIO pio = pio0;
    uint sm = pio_claim_unused_sm(pio, true);

    pio_sm_config_xfer(pio, sm, PIO_DIR_TO_SM, 256, 1);

    uint offset = pio_add_program(pio, &dcc_wave_program);

    dcc_wave_program_init(pio, sm, offset, PIN_BASE);

    pio_sm_clear_fifos(pio, sm);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    printf("RP1 PIO DCC ready\n");
    printf("GPIO24 -> IN3 main track high\n");
    printf("GPIO23 -> IN4 main track low\n");
    printf("GPIO25 -> ENB\n");
    printf("Commands: f r s x q\n");

    while (running)
    {
        handle_keyboard();

        if (track_on)
            send_packet(pio, sm, LOCO_ADDR, data_byte, one_count, zero_count);
        else
            usleep(1000);
    }

    set_track(false);
    lgGpiochipClose(h);

    return 0;
}