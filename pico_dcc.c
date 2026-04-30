#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "dcc_wave.pio.h"

#define PIN_IN1 2
#define PIN_IN2 3
#define PIN_ENA 4

#define LOCO_ADDR 3

#define DCC_ONE_US 58
#define DCC_ZERO_US 100

static uint8_t data_byte = 0x60;
static bool track_on = false;

static inline uint32_t count_from_us(uint32_t us)
{
    return us > 2 ? us - 2 : 1;
}

static void send_bit(PIO pio, int sm, int bit, uint32_t one_count, uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;

    pio_sm_put_blocking(pio, sm, count);
    pio_sm_put_blocking(pio, sm, count);
}

static void send_byte(PIO pio, int sm, uint8_t b, uint32_t one_count, uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
    {
        send_bit(pio, sm, (b >> i) & 1, one_count, zero_count);
    }
}

static void send_packet(PIO pio, int sm, uint32_t one_count, uint32_t zero_count)
{
    uint8_t checksum = LOCO_ADDR ^ data_byte;

    for (int i = 0; i < 14; i++)
    {
        send_bit(pio, sm, 1, one_count, zero_count);
    }

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, LOCO_ADDR, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, data_byte, one_count, zero_count);

    send_bit(pio, sm, 0, one_count, zero_count);
    send_byte(pio, sm, checksum, one_count, zero_count);

    send_bit(pio, sm, 1, one_count, zero_count);
}

static void set_track(bool on)
{
    track_on = on;
    gpio_put(PIN_ENA, on ? 1 : 0);
}

static void handle_cmd(int c)
{
    if (c == 'f' || c == 'F')
    {
        data_byte = 0x63;
        set_track(true);
        printf("FORWARD: 03 63 60\n");
    }
    else if (c == 'r' || c == 'R')
    {
        data_byte = 0x43;
        set_track(true);
        printf("REVERSE: 03 43 40\n");
    }
    else if (c == 's' || c == 'S')
    {
        data_byte = 0x60;
        set_track(true);
        printf("STOP: 03 60 63\n");
    }
    else if (c == 'x' || c == 'X')
    {
        set_track(false);
        printf("TRACK OFF\n");
    }
}

int main()
{
    stdio_init_all();
    sleep_ms(2000);

    gpio_init(PIN_ENA);
    gpio_set_dir(PIN_ENA, GPIO_OUT);
    gpio_put(PIN_ENA, 0);

    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &dcc_wave_program);

    pio_gpio_init(pio, PIN_IN1);
    pio_gpio_init(pio, PIN_IN2);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_IN1, 2, true);

    pio_sm_config c = dcc_wave_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, PIN_IN1);

    // 125 MHz / 125 = 1 MHz, so 1 PIO cycle = 1 us
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    printf("Pico DCC ready\n");
    printf("GPIO2=IN1, GPIO3=IN2, GPIO4=ENA\n");
    printf("Commands: f r s x\n");

    while (1)
    {
        int c_in = getchar_timeout_us(0);

        if (c_in != PICO_ERROR_TIMEOUT)
        {
            handle_cmd(c_in);
        }

        if (track_on)
        {
            send_packet(pio, sm, one_count, zero_count);
        }
        else
        {
            sleep_ms(1);
        }
    }
}