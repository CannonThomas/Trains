/*
 * dcc_l298_pi5_gpiod_rt.c
 *
 * Raspberry Pi 5 + L298 DCC test using libgpiod + realtime busy timing.
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
 *   x = ENA off
 *   q = quit
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <time.h>
#include <sched.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <gpiod.h>

#define CHIP_NAME "gpiochip0"

#define PIN_ENA 18
#define PIN_IN2 23
#define PIN_IN1 24

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static struct gpiod_chip *chip = NULL;
static struct gpiod_line *line_ena = NULL;
static struct gpiod_line *line_in1 = NULL;
static struct gpiod_line *line_in2 = NULL;

static volatile bool running = true;
static bool track_on = true;
static char mode = 'f';

static void cleanup(void);

static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return ((uint64_t)ts.tv_sec * 1000000000ULL) + ts.tv_nsec;
}

static void delay_us_busy(uint32_t us)
{
    uint64_t end = now_ns() + ((uint64_t)us * 1000ULL);
    while (now_ns() < end)
    {
        // busy wait for tighter timing than nanosleep/usleep
    }
}

static void handle_sigint(int sig)
{
    (void)sig;
    running = false;
}

static void set_realtime(void)
{
    struct sched_param sp;
    sp.sched_priority = 80;

    if (sched_setscheduler(0, SCHED_FIFO, &sp) != 0)
    {
        perror("Warning: failed to set SCHED_FIFO");
    }

    if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0)
    {
        perror("Warning: failed to lock memory");
    }
}

static void set_rails(int state)
{
    if (state)
    {
        gpiod_line_set_value(line_in1, 1);
        gpiod_line_set_value(line_in2, 0);
    }
    else
    {
        gpiod_line_set_value(line_in1, 0);
        gpiod_line_set_value(line_in2, 1);
    }
}

static void send_bit(int bit)
{
    uint32_t us = bit ? DCC_ONE_US : DCC_ZERO_US;

    set_rails(0);
    delay_us_busy(us);

    set_rails(1);
    delay_us_busy(us);
}

static void send_byte(uint8_t b)
{
    for (int i = 7; i >= 0; i--)
    {
        send_bit((b >> i) & 1);
    }
}

static void send_packet(uint8_t addr, uint8_t data)
{
    uint8_t checksum = addr ^ data;

    for (int i = 0; i < 14; i++)
    {
        send_bit(1);
    }

    send_bit(0);
    send_byte(addr);

    send_bit(0);
    send_byte(data);

    send_bit(0);
    send_byte(checksum);

    send_bit(1);
}

static void send_forward(void)
{
    send_packet(LOCO_ADDR, 0x63);
}

static void send_reverse(void)
{
    send_packet(LOCO_ADDR, 0x43);
}

static void send_stop(void)
{
    send_packet(LOCO_ADDR, 0x60);
}

static void send_idle(void)
{
    send_packet(0xFF, 0x00);
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
        gpiod_line_set_value(line_ena, 1);
        printf("\nFORWARD: 03 63 60\n");
    }
    else if (c == 'r' || c == 'R')
    {
        mode = 'r';
        track_on = true;
        gpiod_line_set_value(line_ena, 1);
        printf("\nREVERSE: 03 43 40\n");
    }
    else if (c == 's' || c == 'S')
    {
        mode = 's';
        track_on = true;
        gpiod_line_set_value(line_ena, 1);
        printf("\nSTOP PACKETS: 03 60 63\n");
    }
    else if (c == 'i' || c == 'I')
    {
        mode = 'i';
        track_on = true;
        gpiod_line_set_value(line_ena, 1);
        printf("\nIDLE PACKETS: FF 00 FF\n");
    }
    else if (c == 'x' || c == 'X')
    {
        track_on = false;
        gpiod_line_set_value(line_ena, 0);
        gpiod_line_set_value(line_in1, 0);
        gpiod_line_set_value(line_in2, 0);
        printf("\nTRACK OFF / ENA OFF\n");
    }
    else if (c == 'q' || c == 'Q')
    {
        running = false;
    }

    fflush(stdout);
}

static int setup_gpio(void)
{
    chip = gpiod_chip_open_by_name(CHIP_NAME);
    if (!chip)
    {
        perror("Failed to open gpiochip0");
        return -1;
    }

    line_ena = gpiod_chip_get_line(chip, PIN_ENA);
    line_in1 = gpiod_chip_get_line(chip, PIN_IN1);
    line_in2 = gpiod_chip_get_line(chip, PIN_IN2);

    if (!line_ena || !line_in1 || !line_in2)
    {
        printf("Failed to get GPIO lines\n");
        return -1;
    }

    if (gpiod_line_request_output(line_ena, "dcc_ena", 0) < 0)
    {
        perror("Failed to request ENA");
        return -1;
    }

    if (gpiod_line_request_output(line_in1, "dcc_in1", 0) < 0)
    {
        perror("Failed to request IN1");
        return -1;
    }

    if (gpiod_line_request_output(line_in2, "dcc_in2", 0) < 0)
    {
        perror("Failed to request IN2");
        return -1;
    }

    gpiod_line_set_value(line_ena, 1);
    set_rails(1);

    return 0;
}

static void cleanup(void)
{
    printf("\nCleaning up GPIO...\n");

    if (line_ena)
    {
        gpiod_line_set_value(line_ena, 0);
        gpiod_line_release(line_ena);
    }

    if (line_in1)
    {
        gpiod_line_set_value(line_in1, 0);
        gpiod_line_release(line_in1);
    }

    if (line_in2)
    {
        gpiod_line_set_value(line_in2, 0);
        gpiod_line_release(line_in2);
    }

    if (chip)
    {
        gpiod_chip_close(chip);
    }
}

int main(void)
{
    signal(SIGINT, handle_sigint);
    atexit(cleanup);

    set_realtime();

    if (setup_gpio() < 0)
    {
        return 1;
    }

    printf("=====================================\n");
    printf("Pi 5 DCC gpiod realtime test\n");
    printf("GPIO18 = ENA\n");
    printf("GPIO23 = IN2\n");
    printf("GPIO24 = IN1\n");
    printf("J3/J4  = rails\n");
    printf("Commands: f r s i x q\n");
    printf("Starting FORWARD packets: 03 63 60\n");
    printf("=====================================\n");

    for (int i = 0; i < 100; i++)
    {
        send_idle();
    }

    while (running)
    {
        check_keyboard();

        if (!track_on)
        {
            usleep(1000);
            continue;
        }

        if (mode == 'f')
        {
            send_forward();
        }
        else if (mode == 'r')
        {
            send_reverse();
        }
        else if (mode == 's')
        {
            send_stop();
        }
        else
        {
            send_idle();
        }
    }

    return 0;
}