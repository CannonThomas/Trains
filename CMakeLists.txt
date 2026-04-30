cmake_minimum_required(VERSION 3.10)

project(pi5_pio_dcc C)

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/dcc_wave.pio.h
    COMMAND pioasm -o c-sdk ${CMAKE_CURRENT_SOURCE_DIR}/dcc_wave.pio ${CMAKE_CURRENT_BINARY_DIR}/dcc_wave.pio.h
    DEP