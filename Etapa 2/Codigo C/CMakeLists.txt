cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()

set(PICO_BOARD pico2 CACHE STRING "Board type")

include(pico_sdk_import.cmake)

project(ADC_Prueba C CXX ASM)

pico_sdk_init()

add_executable(ADC_Prueba
    main.c
    fft.c
    sh1106.c
)

pico_set_program_name(ADC_Prueba "ADC_Prueba")
pico_set_program_version(ADC_Prueba "0.1")

# Si no usas PIO elimina la siguiente línea o pon el archivo correcto
# pico_generate_pio_header(ADC_Prueba ${CMAKE_CURRENT_LIST_DIR}/blink.pio)

# Habilitar stdio por USB (ajusta según prefieras)
pico_enable_stdio_uart(ADC_Prueba 0)
pico_enable_stdio_usb(ADC_Prueba 1)

target_link_libraries(ADC_Prueba
    pico_stdlib
    hardware_adc
    hardware_dma
    hardware_irq
    hardware_uart
    hardware_i2c
)

target_include_directories(ADC_Prueba PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
)

pico_add_extra_outputs(ADC_Prueba)
