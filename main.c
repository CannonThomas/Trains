#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include <stdbool.h>

#include "piolib.h"

#define PIN_IN2 23
#define PIN_IN1 24
#define PIN_ENA 18

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static inline void delay_us(uint32_t us)
{
    usleep(us);
}

static inline void dcc_one(void)
{
    gpio_put(PIN_IN2, 1);
    gpio_put(PIN_IN1, 0);
    delay_us(DCC_ONE_US);

    gpio_put(PIN_IN2, 0);
    gpio_put(PIN_IN1, 1);
    delay_us(DCC_ONE_US);
}

static inline void dcc_zero(void)
{
    gpio_put(PIN_IN2, 1);
    gpio_put(PIN_IN1, 0);
    delay_us(DCC_ZERO_US);

    gpio_put(PIN_IN2, 0);
    gpio_put(PIN_IN1, 1);
    delay_us(DCC_ZERO_US);
}

static void send_bit(int bit)
{
    if (bit)
        dcc_one();
    else
        dcc_zero();
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

int main(void)
{
    gpio_init(PIN_IN2);
    gpio_init(PIN_IN1);
    gpio_init(PIN_ENA);

    gpio_set_dir(PIN_IN2, GPIO_OUT);
    gpio_set_dir(PIN_IN1, GPIO_OUT);
    gpio_set_dir(PIN_ENA, GPIO_OUT);

    gpio_put(PIN_ENA, 1);

    printf("DCC TEST START\n");

    while (1)
    {
        send_packet(3, 0x63); // forward
    }

    return 0;
}