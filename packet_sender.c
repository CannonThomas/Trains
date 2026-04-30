#include "packet_sender.h"

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <lgpio.h>

#include "piolib.h"
#include "dcc_wave.pio.h"

#define GPIOCHIP 0

// L298 enable pin
#define ENB 25

// PIO output pins must be consecutive:
// GPIO23 = PIO bit0
// GPIO24 = PIO bit1
#define PIN_BASE 23

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static int h = -1;
static PIO pio = pio0;
static uint sm = 0;
static bool initialized = false;

static uint32_t count_from_us(uint32_t us)
{
    // Tune this if scope shows timing slightly off.
    return us > 4 ? us - 4 : 1;
}

static void dcc_wave_init(PIO pio_inst, uint sm_id, uint offset, uint pin_base)
{
    pio_gpio_init(pio_inst, pin_base);
    pio_gpio_init(pio_inst, pin_base + 1);

    pio_sm_set_consecutive_pindirs(pio_inst, sm_id, pin_base, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);

    // dcc_wave.pio uses set pins, 1 and set pins, 2
    sm_config_set_set_pins(&c, pin_base, 2);

    // 125 MHz / 125 = about 1 MHz
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio_inst, sm_id, offset, &c);
}

static void send_bit(int bit)
{
    uint32_t count = bit ? count_from_us(DCC_ONE_US) : count_from_us(DCC_ZERO_US);

    // First half-cycle: PIO set pins, 1 -> GPIO23=1 GPIO24=0
    pio_sm_put_blocking(pio, sm, count);

    // Second half-cycle: PIO set pins, 2 -> GPIO23=0 GPIO24=1
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(uint8_t bytes, int count)
{
    uint8_t mask = 0x01 << (count - 1);

    for (int i = 0; i < count; i++)
    {
        send_bit((bytes & mask) ? 1 : 0);
        mask >>= 1;
    }
}

static void send_packet(uint8_t addr, uint8_t data)
{
    uint8_t preamble = 0xFF;
    uint8_t start = 0x00;
    uint8_t end = 0x01;
    uint8_t error = addr ^ data;

    // Same style as previous group: 8 preamble ones + 4 preamble ones
    send_byte(preamble, 8);
    send_byte(preamble, 4);

    send_byte(start, 1);
    send_byte(addr, 8);

    send_byte(start, 1);
    send_byte(data, 8);

    send_byte(start, 1);
    send_byte(error, 8);

    send_byte(end, 1);
}

int initialize(void)
{
    if (initialized)
        return 0;

    h = lgGpiochipOpen(GPIOCHIP);
    if (h < 0)
    {
        printf("Failed to open lgpio chip\n");
        return -1;
    }

    if (lgGpioClaimOutput(h, 0, ENB, 1) < 0)
    {
        printf("Failed to claim ENB GPIO%d\n", ENB);
        lgGpiochipClose(h);
        h = -1;
        return -1;
    }

    pio = pio0;

    sm = pio_claim_unused_sm(pio, true);
    printf("Claimed SM: %u\n", sm);

    uint offset = pio_add_program(pio, &dcc_wave_program);
    printf("Loaded PIO program at offset: %u\n", offset);

    dcc_wave_init(pio, sm, offset, PIN_BASE);

    pio_sm_clear_fifos(pio, sm);
    pio_sm_set_enabled(pio, sm, true);

    initialized = true;

    printf("RP1 PIO DCC initialized\n");
    printf("GPIO23 -> L298 input A\n");
    printf("GPIO24 -> L298 input B\n");
    printf("GPIO25 -> ENB\n");

    return 0;
}

void forward(int n)
{
    if (!initialized)
        return;

    for (int i = 0; i < n; i++)
    {
        // 03 63 60
        send_packet(0x03, 0x63);
    }
}

void backward(int n)
{
    if (!initialized)
        return;

    for (int i = 0; i < n; i++)
    {
        // 03 43 40
        send_packet(0x03, 0x43);
    }
}

void stop(int n)
{
    if (!initialized)
        return;

    for (int i = 0; i < n; i++)
    {
        // 03 60 63
        send_packet(0x03, 0x60);
    }
}

void idle(int n)
{
    if (!initialized)
        return;

    for (int i = 0; i < n; i++)
    {
        // FF 00 FF
        send_packet(0xFF, 0x00);
    }
}

void function(int n, int type)
{
    if (!initialized)
        return;

    uint8_t addr = 0x03;
    uint8_t header = 0x80;
    uint8_t mask;

    if (type >= 5)
    {
        header = 0xB0;
        mask = 0x01 << (type - 5);
    }
    else
    {
        mask = 0x01 << type;
    }

    uint8_t data = header | mask;

    for (int i = 0; i < n; i++)
    {
        send_packet(addr, data);
    }
}

int terminate(void)
{
    if (h >= 0)
    {
        lgGpioWrite(h, ENB, 0);
        lgGpiochipClose(h);
        h = -1;
    }

    initialized = false;
    printf("RP1 PIO DCC terminated\n");

    return 0;
}