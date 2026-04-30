#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <sys/select.h>
#include <lgpio.h>

#define GPIOCHIP 0

#define ENA 18
#define ENB 25

// Turntable channel from PDF
#define IN1 24
#define IN2 23

// Main track channel from PDF
#define IN3 22
#define IN4 27

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static int h = -1;
static volatile bool running = true;
static bool track_on = false;
static uint8_t data_byte = 0x60;

static void delay_us(long us)
{
    struct timespec ts;
    ts.tv_sec = us / 1000000;
    ts.tv_nsec = (us % 1000000) * 1000;
    nanosleep(&ts, NULL);
}

static void set_enable(bool on)
{
    lgGpioWrite(h, ENA, on ? 1 : 0);
    lgGpioWrite(h, ENB, on ? 1 : 0);
}

/*
 * PDF mapping:
 * IN1/IN2 = turntable high/low
 * IN3/IN4 = main track high/low
 *
 * So main track DCC must be IN3 opposite IN4.
 * We mirror IN1/IN2 too only in case your physical rails use both outputs.
 */
static void set_polarity(int state)
{
    if (state)
    {
        // State A: high side pins ON, low side pins OFF
        lgGpioWrite(h, IN1, 1);
        lgGpioWrite(h, IN2, 0);

        lgGpioWrite(h, IN3, 1);
        lgGpioWrite(h, IN4, 0);
    }
    else
    {
        // State B: high side pins OFF, low side pins ON
        lgGpioWrite(h, IN1, 0);
        lgGpioWrite(h, IN2, 1);

        lgGpioWrite(h, IN3, 0);
        lgGpioWrite(h, IN4, 1);
    }
}

static void send_bit(int bit)
{
    int us = bit ? DCC_ONE_US : DCC_ZERO_US;

    set_polarity(0);
    delay_us(us);

    set_polarity(1);
    delay_us(us);
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
        send_bit(1);

    send_bit(0);
    send_byte(addr);

    send_bit(0);
    send_byte(data);

    send_bit(0);
    send_byte(checksum);

    send_bit(1);
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
        track_on = true;
        set_enable(true);
        printf("\nFORWARD: 03 63 60\n");
    }
    else if (c == 'r' || c == 'R')
    {
        data_byte = 0x43;
        track_on = true;
        set_enable(true);
        printf("\nREVERSE: 03 43 40\n");
    }
    else if (c == 's' || c == 'S')
    {
        data_byte = 0x60;
        track_on = true;
        set_enable(true);
        printf("\nSTOP: 03 60 63\n");
    }
    else if (c == 'x' || c == 'X')
    {
        track_on = false;
        set_enable(false);
        printf("\nTRACK OFF\n");
    }
    else if (c == 'q' || c == 'Q')
    {
        running = false;
    }

    fflush(stdout);
}

static void cleanup(void)
{
    if (h >= 0)
    {
        set_enable(false);

        lgGpioWrite(h, IN1, 0);
        lgGpioWrite(h, IN2, 0);
        lgGpioWrite(h, IN3, 0);
        lgGpioWrite(h, IN4, 0);

        lgGpiochipClose(h);
    }
}

int main(void)
{
    signal(SIGINT, SIG_DFL);

    h = lgGpiochipOpen(GPIOCHIP);

    if (h < 0)
    {
        printf("Failed to open gpiochip\n");
        return 1;
    }

    lgGpioClaimOutput(h, 0, ENA, 0);
    lgGpioClaimOutput(h, 0, ENB, 0);

    lgGpioClaimOutput(h, 0, IN1, 0);
    lgGpioClaimOutput(h, 0, IN2, 0);
    lgGpioClaimOutput(h, 0, IN3, 0);
    lgGpioClaimOutput(h, 0, IN4, 0);

    printf("4-input L298 DCC test ready\n");
    printf("ENA=18 ENB=25\n");
    printf("Turntable: IN1=24 IN2=23\n");
    printf("Main track: IN3=22 IN4=27\n");
    printf("Commands: f r s x q\n");

    while (running)
    {
        handle_keyboard();

        if (track_on)
            send_packet(LOCO_ADDR, data_byte);
        else
            usleep(1000);
    }

    cleanup();
    return 0;
}