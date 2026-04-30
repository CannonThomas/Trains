#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/select.h>

#include "piolib.h"
#include "hardware/pio_instructions.h"
#include <lgpio.h>

#define PIN_ENA 18
#define PIN_IN2 23
#define PIN_IN1 24

#define LOCO_ADDR 3
#define DCC_ONE_US 58
#define DCC_ZERO_US 100

#define GPIOCHIP 0

static int gpio_handle = -1;
static uint32_t txbuf[512];
static int txlen = 0;
static uint8_t data_byte = 0x60;
static bool track_on = false;

static inline uint16_t ss(uint value)
{
    return pio_encode_sideset(2, value);
}

static void build_pio_program(uint16_t instr[6])
{
    instr[0] = pio_encode_pull(false, true) | ss(0b01);
    instr[1] = pio_encode_mov(pio_x, pio_osr) | ss(0b01);
    instr[2] = pio_encode_jmp_x_dec(2) | ss(0b01);

    instr[3] = pio_encode_pull(false, true) | ss(0b10);
    instr[4] = pio_encode_mov(pio_x, pio_osr) | ss(0b10);
    instr[5] = pio_encode_jmp_x_dec(5) | ss(0b10);
}

static uint32_t count_from_us(uint32_t us)
{
    return us > 3 ? us - 3 : 1;
}

static void add_half(uint32_t count)
{
    if (txlen < 512)
    {
        txbuf[txlen++] = count;
    }
}

static void add_bit(int bit, uint32_t one_count, uint32_t zero_count)
{
    uint32_t count = bit ? one_count : zero_count;
    add_half(count);
    add_half(count);
}

static void add_byte(uint8_t b, uint32_t one_count, uint32_t zero_count)
{
    for (int i = 7; i >= 0; i--)
    {
        add_bit((b >> i) & 1, one_count, zero_count);
    }
}

static int build_packet(uint8_t addr, uint8_t data,
                        uint32_t one_count,
                        uint32_t zero_count)
{
    uint8_t checksum = addr ^ data;

    txlen = 0;

    for (int i = 0; i < 14; i++)
    {
        add_bit(1, one_count, zero_count);
    }

    add_bit(0, one_count, zero_count);
    add_byte(addr, one_count, zero_count);

    add_bit(0, one_count, zero_count);
    add_byte(data, one_count, zero_count);

    add_bit(0, one_count, zero_count);
    add_byte(checksum, one_count, zero_count);

    add_bit(1, one_count, zero_count);

    return txlen * sizeof(uint32_t);
}

static void set_track(bool on)
{
    track_on = on;
    lgGpioWrite(gpio_handle, PIN_ENA, on ? 1 : 0);
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
        printf("\nSTOP: 03 60 63\n");
    }
    else if (c == 'x' || c == 'X')
    {
        set_track(false);
        printf("\nTRACK OFF\n");
    }

    fflush(stdout);
}

int main(void)
{
    uint16_t instructions[6];

    gpio_handle = lgGpiochipOpen(GPIOCHIP);
    if (gpio_handle < 0)
    {
        printf("Failed to open lgpio chip\n");
        return 1;
    }

    lgGpioClaimOutput(gpio_handle, 0, PIN_ENA, 0);

    build_pio_program(instructions);

    struct pio_program dcc_program = {
        .instructions = instructions,
        .length = 6,
        .origin = 0
    };

    PIO pio = pio0;
    int sm = pio_claim_unused_sm(pio, true);

    pio_sm_config_xfer(pio, sm, PIO_DIR_TO_SM, sizeof(txbuf), 1);

    uint offset = pio_add_program(pio, &dcc_program);

    pio_gpio_init(pio, PIN_IN2);
    pio_gpio_init(pio, PIN_IN1);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_IN2, 2, true);

    pio_sm_config c = pio_get_default_sm_config();

    sm_config_set_wrap(&c, offset + 0, offset + 5);
    sm_config_set_sideset(&c, 2, false, false);
    sm_config_set_sideset_pins(&c, PIN_IN2);
    sm_config_set_clkdiv(&c, 125.0f);

    pio_sm_clear_fifos(pio, sm);
    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);

    uint32_t one_count = count_from_us(DCC_ONE_US);
    uint32_t zero_count = count_from_us(DCC_ZERO_US);

    printf("Pi 5 RP1 PIO DCC ready\n");
    printf("GPIO18 = ENA\n");
    printf("GPIO23 = IN2\n");
    printf("GPIO24 = IN1\n");
    printf("Commands: f r s x\n");

    while (1)
    {
        handle_keyboard();

        if (track_on)
        {
            int bytes = build_packet(LOCO_ADDR, data_byte, one_count, zero_count);
            pio_sm_xfer_data(pio, sm, PIO_DIR_TO_SM, bytes, (uint8_t *)txbuf);
        }
        else
        {
            usleep(1000);
        }
    }

    return 0;
}