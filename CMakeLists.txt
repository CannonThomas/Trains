cmake_minimum_required(VERSION 3.10)

project(pi5_pio_dcc C)

add_executable(pi5_pio_dcc main.c)

# Link against PIOLib
target_link_libraries(pi5_pio_dcc pio)