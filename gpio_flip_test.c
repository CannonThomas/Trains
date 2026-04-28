#include <stdio.h>
#include <unistd.h>
#include <gpiod.h>

#define PIN_EN 18
#define PIN_IN1 23
#define PIN_IN2 24

int main() {
    struct gpiod_chip *chip = gpiod_chip_open("/dev/gpiochip0");
    if (!chip) {
        printf("Failed to open gpiochip0\n");
        return 1;
    }

    struct gpiod_line *en  = gpiod_chip_get_line(chip, PIN_EN);
    struct gpiod_line *in1 = gpiod_chip_get_line(chip, PIN_IN1);
    struct gpiod_line *in2 = gpiod_chip_get_line(chip, PIN_IN2);

    if (!en || !in1 || !in2) {
        printf("Failed to get GPIO lines\n");
        return 1;
    }

    gpiod_line_request_output(en,  "test_en",  1);
    gpiod_line_request_output(in1, "test_in1", 0);
    gpiod_line_request_output(in2, "test_in2", 0);

    printf("GPIO flip test running\n");
    printf("GPIO23/IN1 and GPIO24/IN2 should be opposite every 1 second\n");

    while (1) {
        printf("IN1 HIGH, IN2 LOW\n");
        gpiod_line_set_value(in1, 1);
        gpiod_line_set_value(in2, 0);
        sleep(1);

        printf("IN1 LOW, IN2 HIGH\n");
        gpiod_line_set_value(in1, 0);
        gpiod_line_set_value(in2, 1);
        sleep(1);
    }

    return 0;
}