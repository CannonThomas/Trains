cmake_minimum_required(VERSION 3.10)

project(pi5_pio_dcc C)

add_executable(pi5_pio_dcc main.c)

# Tell compiler where headers are
target_include_directories(pi5_pio_dcc PRIVATE /usr/local/include)

# Link PIOLib
target_link_libraries(pi5_pio_dcc piolib)