#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <signal.h>
#include <time.h>
#include <lgpio.h>

#define GPIOCHIP 0

#define ENA 18
#define IN2 23
#define IN1 24

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static int h = -1;
static volatile bool running = true;

void cleanup(void);

void handle_sigint(int sig)
{
    (void)sig;
    running = false;
}

static void delay_us(long us)
{
    struct timespec ts;
    ts.tv_sec = us / 1000000;
    ts.tv_nsec = (us % 1000000) * 1000;
    nanosleep(&ts, NULL);
}

/*
 * THIS IS THE IMPORTANT PART:
 * IN1 and IN2 are ALWAYS opposite.
 */
static void set_polarity(int state)
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

static void send_dcc_bit(int bit)
{
    int us = bit ? DCC_ONE_US : DCC_ZERO_US;

    // First rail polarity
    set_polarity(0);
    delay_us(us);

    // Opposite rail polarity
    set_polarity(1);
    delay_us(us);
}

static void send_dcc_byte(uint8_t b)
{
    for (int i = 7; i >= 0; i--)
    {
        send_dcc_bit((b >> i) & 1);
    }
}

static void send_dcc_packet(uint8_t addr, uint8_t data)
{
    uint8_t checksum = addr ^ data;

    // Preamble
    for (int i = 0; i < 14; i++)
    {
        send_dcc_bit(1);
    }

    send_dcc_bit(0);
    send_dcc_byte(addr);

    send_dcc_bit(0);
    send_dcc_byte(data);

    send_dcc_bit(0);
    send_dcc_byte(checksum);

    send_dcc_bit(1);
}

static void send_forward(void)
{
    // packet: 03 63 60
    send_dcc_packet(LOCO_ADDR, 0x63);
}

static void send_reverse(void)
{
    // packet: 03 43 40
    send_dcc_packet(LOCO_ADDR, 0x43);
}

static void send_stop(void)
{
    // packet: 03 60 63
    send_dcc_packet(LOCO_ADDR, 0x60);
}

int setup_gpio(void)
{
    h = lgGpiochipOpen(GPIOCHIP);

    if (h < 0)
    {
        printf("Failed to open gpiochip\n");
        return -1;
    }

    lgGpioClaimOutput(h, 0, ENA, 0);
    lgGpioClaimOutput(h, 0, IN1, 0);
    lgGpioClaimOutput(h, 0, IN2, 0);

    lgGpioWrite(h, ENA, 1);

    // Start with known opposite state
    set_polarity(1);

    return 0;
}

void cleanup(void)
{
    if (h >= 0)
    {
        lgGpioWrite(h, ENA, 0);
        lgGpioWrite(h, IN1, 0);
        lgGpioWrite(h, IN2, 0);
        lgGpiochipClose(h);
    }
}

int main(int argc, char *argv[])
{
    char mode = 'f';

    if (argc >= 2)
    {
        mode = argv[1][0];
    }

    signal(SIGINT, handle_sigint);

    if (setup_gpio() < 0)
    {
        return 1;
    }

    printf("Real DCC polarity test running\n");
    printf("GPIO18=ENA, GPIO24=IN1, GPIO23=IN2\n");
    printf("Scope: tip on J3, ground clip on J4\n");
    printf("Mode: %c\n", mode);
    printf("CTRL+C to stop\n");

    while (running)
    {
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
            send_stop();
        }
    }

    cleanup();
    return 0;
}