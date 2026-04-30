cmake_minimum_required(VERSION 3.10)

project(pi5_pio_dcc C)

add_executable(pi5_pio_dcc
    main.c
)

target_include_directories(pi5_pio_dcc PRIVATE
    /usr/local/include/piolib
    ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(pi5_pio_dcc
    pio
    lgpio
)