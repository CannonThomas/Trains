cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(pico_dcc C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(pico_dcc
    pico_dcc.c
)

pico_generate_pio_header(pico_dcc
    ${CMAKE_CURRENT_LIST_DIR}/dcc_wave.pio
)

target_link_libraries(pico_dcc
    pico_stdlib
    hardware_pio
)

pico_enable_stdio_usb(pico_dcc 1)
pico_enable_stdio_uart(pico_dcc 0)

pico_add_extra_outputs(pico_dcc)