#include <stdio.h>
#include <unistd.h>
#include <lgpio.h>

#define GPIOCHIP 0

#define ENA 18
#define IN2 23
#define IN1 24

int main()
{
    int h = lgGpiochipOpen(GPIOCHIP);

    if (h < 0)
    {
        printf("Failed to open gpiochip\n");
        return 1;
    }

    lgGpioClaimOutput(h, 0, ENA, 0);
    lgGpioClaimOutput(h, 0, IN1, 0);
    lgGpioClaimOutput(h, 0, IN2, 0);

    lgGpioWrite(h, ENA, 1);

    printf("L298 polarity test running\n");
    printf("Scope tip on J3, ground clip on J4\n");
    printf("You should see +V for 2 sec, then -V for 2 sec\n");

    while (1)
    {
        // Polarity A
        lgGpioWrite(h, IN1, 1);
        lgGpioWrite(h, IN2, 0);
        printf("IN1=1 IN2=0\n");
        sleep(2);

        // Polarity B
        lgGpioWrite(h, IN1, 0);
        lgGpioWrite(h, IN2, 1);
        printf("IN1=0 IN2=1\n");
        sleep(2);
    }

    lgGpiochipClose(h);
    return 0;
}