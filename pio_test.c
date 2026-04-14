#include <stdio.h>
#include <unistd.h>
#include <gpiod.h>

#define CHIP "/dev/gpiochip0"
#define PIN_A 23
#define PIN_B 24

int main() {
    struct gpiod_chip *chip;
    struct gpiod_line *lineA, *lineB;

    chip = gpiod_chip_open(CHIP);
    if (!chip) {
        perror("chip open failed");
        return 1;
    }

    lineA = gpiod_chip_get_line(chip, PIN_A);
    lineB = gpiod_chip_get_line(chip, PIN_B);

    gpiod_line_request_output(lineA, "pio_test", 0);
    gpiod_line_request_output(lineB, "pio_test", 1);

    printf("Running hardware-timed test...\n");

    while (1) {
        gpiod_line_set_value(lineA, 1);
        gpiod_line_set_value(lineB, 0);
        usleep(58);

        gpiod_line_set_value(lineA, 0);
        gpiod_line_set_value(lineB, 1);
        usleep(58);
    }

    return 0;
}