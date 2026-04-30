#include <stdio.h>
#include <unistd.h>

#include "piolib.h"

int main(void)
{
    PIO pio;
    int sm;

    printf("Pi 5 RP1 PIOLib test starting...\n");

    pio = pio0;
    sm = pio_claim_unused_sm(pio, true);

    printf("Claimed PIO state machine: %d\n", sm);
    printf("PIOLib is compiling/linking correctly.\n");

    while (1)
    {
        printf("PIO alive\n");
        sleep(1);
    }

    return 0;
}