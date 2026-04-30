/*
 * dcc_l298_pi5_test.c
 *
 * Raspberry Pi 5 + L298 H-Bridge DCC packet test
 *
 * Wiring:
 *   GPIO18 -> ENA
 *   GPIO24 -> IN1
 *   GPIO23 -> IN2
 *   L298 J3/J4 -> track rails
 *
 * Compile:
 *   gcc dcc_l298_pi5_test.c -o dcc_l298_pi5_test -llgpio
 *
 * Run:
 *   sudo ./dcc_l298_pi5_test f
 *   sudo ./dcc_l298_pi5_test r
 *   sudo ./dcc_l298_pi5_test s
 *   sudo ./dcc_l298_pi5_test i
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <signal.h>
#include <time.h>
#include <lgpio.h>

#define GPIOCHIP 0

#define ENA 18
#define IN1 24
#define IN2 23

#define LOCO_ADDR 3

static int h = -1;
static volatile int running = 1;
static int flip_polarity = 0;

void cleanup(void);

void handle_sigint(int sig)
{
    (void)sig;
    running = 0;
}

static void delay_us(long us)
{
    struct timespec ts;
    ts.tv_sec = us / 1000000;
    ts.tv_nsec = (us % 1000000) * 1000;
    nanosleep(&ts, NULL);
}

static void set_rails(int state)
{
    if (!flip_polarity)
    {
        if (state)
        {
            lgGpioWrite(h, IN1, 1);
            lgGpioWrite(h, IN2, 0);
        }
        else
        {
            lgGpioWrite(h, IN1, 0);
            lgGpioWrite(h, IN2, 1);
        }
    }
    else
    {
        if (state)
        {
            lgGpioWrite(h, IN1, 0);
            lgGpioWrite(h, IN2, 1);
        }
        else
        {
            lgGpioWrite(h, IN1, 1);
            lgGpioWrite(h, IN2, 0);
        }
    }
}

static void send_dcc_bit(int bit)
{
    int us = bit ? 58 : 100;

    set_rails(0);
    delay_us(us);

    set_rails(1);
    delay_us(us);
}

static void send_dcc_byte(uint8_t data)
{
    for (int i = 7; i >= 0; i--)
    {
        send_dcc_bit((data >> i) & 1);
    }
}

static void send_dcc_packet(uint8_t addr, uint8_t data)
{
    uint8_t error = addr ^ data;

    // Preamble: DCC requires at least 10 logic 1 bits.
    // Use 14 for safety.
    for (int i = 0; i < 14; i++)
    {
        send_dcc_bit(1);
    }

    send_dcc_bit(0);
    send_dcc_byte(addr);

    send_dcc_bit(0);
    send_dcc_byte(data);

    send_dcc_bit(0);
    send_dcc_byte(error);

    send_dcc_bit(1);
}

static void send_idle_packet(void)
{
    // Standard-ish idle packet
    send_dcc_packet(0xFF, 0x00);
}

static void send_forward_packet(void)
{
    // Same style as the working reference project:
    // address 3, forward direction, nonzero speed
    send_dcc_packet(LOCO_ADDR, 0b01100011);
}

static void send_reverse_packet(void)
{
    send_dcc_packet(LOCO_ADDR, 0b01000011);
}

static void send_stop_packet(void)
{
    send_dcc_packet(LOCO_ADDR, 0b01100000);
}

static int setup_gpio(void)
{
    h = lgGpiochipOpen(GPIOCHIP);

    if (h < 0)
    {
        printf("ERROR: Could not open gpiochip%d\n", GPIOCHIP);
        return -1;
    }

    if (lgGpioClaimOutput(h, 0, ENA, 0) < 0)
    {
        printf("ERROR: Could not claim GPIO%d ENA\n", ENA);
        return -1;
    }

    if (lgGpioClaimOutput(h, 0, IN1, 0) < 0)
    {
        printf("ERROR: Could not claim GPIO%d IN1\n", IN1);
        return -1;
    }

    if (lgGpioClaimOutput(h, 0, IN2, 0) < 0)
    {
        printf("ERROR: Could not claim GPIO%d IN2\n", IN2);
        return -1;
    }

    // Enable L298
    lgGpioWrite(h, ENA, 1);

    // Start rails in known opposite state
    lgGpioWrite(h, IN1, 1);
    lgGpioWrite(h, IN2, 0);

    return 0;
}

void cleanup(void)
{
    if (h >= 0)
    {
        printf("\nStopping DCC output...\n");

        lgGpioWrite(h, ENA, 0);
        lgGpioWrite(h, IN1, 0);
        lgGpioWrite(h, IN2, 0);

        lgGpiochipClose(h);
        h = -1;
    }
}

int main(int argc, char *argv[])
{
    char mode = 'f';

    signal(SIGINT, handle_sigint);
    atexit(cleanup);

    if (argc >= 2)
    {
        mode = argv[1][0];
    }

    if (argc >= 3)
    {
        flip_polarity = atoi(argv[2]);
    }

    if (setup_gpio() < 0)
    {
        printf("GPIO setup failed.\n");
        return 1;
    }

    printf("====================================\n");
    printf("Pi 5 L298 DCC Test Running\n");
    printf("GPIO18 -> ENA\n");
    printf("GPIO24 -> IN1\n");
    printf("GPIO23 -> IN2\n");
    printf("J3/J4  -> Rails\n");
    printf("Loco Address: %d\n", LOCO_ADDR);
    printf("Mode: %c\n", mode);
    printf("Flip Polarity: %d\n", flip_polarity);
    printf("Press CTRL+C to stop\n");
    printf("====================================\n");

    // Wake decoder with idle packets first
    for (int i = 0; i < 75; i++)
    {
        send_idle_packet();
    }

    while (running)
    {
        if (mode == 'f')
        {
            send_forward_packet();
        }
        else if (mode == 'r')
        {
            send_reverse_packet();
        }
        else if (mode == 's')
        {
            send_stop_packet();
        }
        else
        {
            send_idle_packet();
        }
    }

    return 0;
}