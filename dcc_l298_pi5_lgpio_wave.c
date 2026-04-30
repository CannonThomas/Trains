/*
 * dcc_l298_pi5_lgpio_wave.c
 *
 * Raspberry Pi 5 + L298 DCC test using lgpio group wave output.
 *
 * Wiring:
 *   GPIO18 -> ENA
 *   GPIO23 -> IN2
 *   GPIO24 -> IN1
 *   L298 J3/J4 -> rails
 *
 * Commands while running:
 *   f = forward packet 03 63 60
 *   r = reverse packet 03 43 40
 *   s = stop packet    03 60 63
 *   i = idle packet    FF 00 FF
 *   x = track off
 *   q = quit
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <sys/select.h>
#include <lgpio.h>

#define GPIOCHIP 0

#define PIN_ENA 18
#define PIN_IN2 23
#define PIN_IN1 24

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

#define MAX_PULSES 256

static int h = -1;
static volatile bool running = true;
static bool track_on = true;
static char mode = 'f';

static lgPulse_t pulses[MAX_PULSES];
static int pulse_count = 0;

/*
 * Group order matters.
 * Group leader is GPIO23.
 *
 * GPIO23 = IN2 = group bit 0
 * GPIO24 = IN1 = group bit 1
 *
 * bits value:
 *   0b01 = IN2 high, IN1 low
 *   0b10 = IN2 low,  IN1 high
 *
 * mask 0b11 means update both pins every pulse.
 */
static int group_gpios[2] = {PIN_IN2, PIN_IN1};
static int group_levels[2] = {0, 1};

static void cleanup(void);

static void handle_sigint(int sig)
{
    (void)sig;
    running = false;
}

static void add_half_cycle(uint64_t bits, int delay_us)
{
    if (pulse_count >= MAX_PULSES)
    {
        printf("ERROR: pulse buffer full\n");
        running = false;
        return;
    }

    pulses[pulse_count].bits = bits;
    pulses[pulse_count].mask = 0b11;
    pulses[pulse_count].delay = delay_us;
    pulse_count++;
}

static void add_dcc_bit(int bit)
{
    int us = bit ? DCC_ONE_US : DCC_ZERO_US;

    add_half_cycle(0b01, us);
    add_half_cycle(0b10, us);
}

static void add_dcc_byte(uint8_t b)
{
    for (int i = 7; i >= 0; i--)
    {
        add_dcc_bit((b >> i) & 1);
    }
}

static int build_packet_wave(uint8_t addr, uint8_t data)
{
    uint8_t checksum = addr ^ data;

    pulse_count = 0;

    for (int i = 0; i < 14; i++)
    {
        add_dcc_bit(1);
    }

    add_dcc_bit(0);
    add_dcc_byte(addr);

    add_dcc_bit(0);
    add_dcc_byte(data);

    add_dcc_bit(0);
    add_dcc_byte(checksum);

    add_dcc_bit(1);

    return pulse_count;
}

static void queue_packet(uint8_t addr, uint8_t data)
{
    int n = build_packet_wave(addr, data);

    if (n <= 0 || !running)
    {
        return;
    }

    int room;

    do
    {
        room = lgTxRoom(h, PIN_IN2, LG_TX_WAVE);
        if (room < 0)
        {
            printf("lgTxRoom error: %s (%d)\n", lguErrorText(room), room);
            running = false;
            return;
        }

        if (room == 0)
        {
            lguSleep(0.001);
        }

    } while (room == 0 && running);

    int status = lgTxWave(h, PIN_IN2, n, pulses);

    if (status < 0)
    {
        printf("lgTxWave error: %s (%d)\n", lguErrorText(status), status);
        running = false;
    }
}

static void check_keyboard(void)
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
        mode = 'f';
        track_on = true;
        lgGpioWrite(h, PIN_ENA, 1);
        printf("\nFORWARD: 03 63 60\n");
    }
    else if (c == 'r' || c == 'R')
    {
        mode = 'r';
        track_on = true;
        lgGpioWrite(h, PIN_ENA, 1);
        printf("\nREVERSE: 03 43 40\n");
    }
    else if (c == 's' || c == 'S')
    {
        mode = 's';
        track_on = true;
        lgGpioWrite(h, PIN_ENA, 1);
        printf("\nSTOP: 03 60 63\n");
    }
    else if (c == 'i' || c == 'I')
    {
        mode = 'i';
        track_on = true;
        lgGpioWrite(h, PIN_ENA, 1);
        printf("\nIDLE: FF 00 FF\n");
    }
    else if (c == 'x' || c == 'X')
    {
        track_on = false;
        lgGpioWrite(h, PIN_ENA, 0);
        lgGroupWrite(h, PIN_IN2, 0, 0b11);
        printf("\nTRACK OFF\n");
    }
    else if (c == 'q' || c == 'Q')
    {
        running = false;
    }

    fflush(stdout);
}

static int setup_gpio(void)
{
    h = lgGpiochipOpen(GPIOCHIP);

    if (h < 0)
    {
        printf("ERROR opening gpiochip%d: %s (%d)\n", GPIOCHIP, lguErrorText(h), h);
        return -1;
    }

    int e;

    e = lgGpioClaimOutput(h, 0, PIN_ENA, 0);
    if (e < 0)
    {
        printf("ERROR claiming ENA: %s (%d)\n", lguErrorText(e), e);
        return -1;
    }

    e = lgGroupClaimOutput(h, 0, 2, group_gpios, group_levels);
    if (e < 0)
    {
        printf("ERROR claiming IN1/IN2 group: %s (%d)\n", lguErrorText(e), e);
        return -1;
    }

    lgGpioWrite(h, PIN_ENA, 1);

    return 0;
}

static void cleanup(void)
{
    printf("\nCleaning up...\n");

    if (h >= 0)
    {
        lgGpioWrite(h, PIN_ENA, 0);
        lgGroupWrite(h, PIN_IN2, 0, 0b11);

        lgGroupFree(h, PIN_IN2);
        lgGpioFree(h, PIN_ENA);

        lgGpiochipClose(h);
        h = -1;
    }
}

int main(void)
{
    signal(SIGINT, handle_sigint);
    atexit(cleanup);

    if (setup_gpio() < 0)
    {
        return 1;
    }

    printf("=====================================\n");
    printf("Pi 5 lgpio WAVE DCC test\n");
    printf("GPIO18 = ENA\n");
    printf("GPIO23 = IN2 / group bit0\n");
    printf("GPIO24 = IN1 / group bit1\n");
    printf("Commands: f r s i x q\n");
    printf("Starting FORWARD packets: 03 63 60\n");
    printf("=====================================\n");

    for (int i = 0; i < 40; i++)
    {
        queue_packet(0xFF, 0x00);
    }

    while (running)
    {
        check_keyboard();

        if (!track_on)
        {
            lguSleep(0.001);
            continue;
        }

        if (mode == 'f')
        {
            queue_packet(LOCO_ADDR, 0x63);
        }
        else if (mode == 'r')
        {
            queue_packet(LOCO_ADDR, 0x43);
        }
        else if (mode == 's')
        {
            queue_packet(LOCO_ADDR, 0x60);
        }
        else
        {
            queue_packet(0xFF, 0x00);
        }
    }

    return 0;
}