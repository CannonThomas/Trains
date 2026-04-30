cmake_minimum_required(VERSION 3.10)

project(pi5_pio_dcc C)

find_program(PIOASM pioasm REQUIRED)

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/dcc_wave.pio.h
    COMMAND ${PIOASM} -o c-sdk
            ${CMAKE_CURRENT_SOURCE_DIR}/dcc_wave.pio
            ${CMAKE_CURRENT_BINARY_DIR}/dcc_wave.pio.h
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/dcc_wave.pio
)

add_executable(pi5_pio_dcc
    main.c
    ${CMAKE_CURRENT_BINARY_DIR}/dcc_wave.pio.h
)

target_include_directories(pi5_pio_dcc PRIVATE
    /usr/local/include/piolib
    ${CMAKE_CURRENT_BINARY_DIR}
)

target_link_libraries(pi5_pio_dcc
    pio
)