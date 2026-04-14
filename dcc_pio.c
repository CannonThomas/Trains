#include <stdio.h>
#include <unistd.h>
#include "piolib.h"

#define PIN_A 23
#define PIN_B 24

#define ONE_US 58
#define ZERO_US 116

int main() {
    PIO pio;
    int sm;

    // Claim PIO + state machine
    if (pio_claim_free_sm_and_add_program(&pio, &sm, NULL) < 0) {
        printf("PIO claim failed\n");
        return 1;
    }

    // Set pins
    pio_gpio_init(pio, PIN_A);
    pio_gpio_init(pio, PIN_B);

    pio_sm_set_consecutive_pindirs(pio, sm, PIN_A, 1, true);
    pio_sm_set_consecutive_pindirs(pio, sm, PIN_B, 1, true);

    // Clock divider (adjust if needed)
    pio_sm_set_clkdiv(pio, sm, 125.0f); // ~1MHz timing base

    pio_sm_set_enabled(pio, sm, true);

    printf("Running DCC PIO test...\n");

    while (1) {
        // ONE bit
        pio_sm_put_blocking(pio, sm, (1 << PIN_A));
        usleep(ONE_US);

        pio_sm_put_blocking(pio, sm, (1 << PIN_B));
        usleep(ONE_US);

        // ZERO bit
        pio_sm_put_blocking(pio, sm, (1 << PIN_A));
        usleep(ZERO_US);

        pio_sm_put_blocking(pio, sm, (1 << PIN_B));
        usleep(ZERO_US);
    }

    return 0;
}