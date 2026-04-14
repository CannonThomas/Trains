#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <gpiod.h>

#define CHIP "gpiochip0"

#define PIN_EN 18
#define PIN_A  23
#define PIN_B  24

void sleep_us(int us) {
    struct timespec ts;
    ts.tv_sec = 0;
    ts.tv_nsec = us * 1000;
    nanosleep(&ts, NULL);
}

int main() {
    struct gpiod_chip *chip;
    struct gpiod_line *ena, *a, *b;

    chip = gpiod_chip_open_by_name(CHIP);

    ena = gpiod_chip_get_line(chip, PIN_EN);
    a   = gpiod_chip_get_line(chip, PIN_A);
    b   = gpiod_chip_get_line(chip, PIN_B);

    gpiod_line_request_output(ena, "dcc", 1);
    gpiod_line_request_output(a, "dcc", 0);
    gpiod_line_request_output(b, "dcc", 0);

    int us;

    while (scanf("%d", &us) != EOF) {
        // A = 1, B = 0
        gpiod_line_set_value(a, 1);
        gpiod_line_set_value(b, 0);
        sleep_us(us);

        // A = 0, B = 1
        gpiod_line_set_value(a, 0);
        gpiod_line_set_value(b, 1);
        sleep_us(us);
    }

    gpiod_line_set_value(ena, 0);

    return 0;
}