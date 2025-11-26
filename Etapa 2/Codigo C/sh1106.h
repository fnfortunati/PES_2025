#ifndef SH1106_H
#define SH1106_H

#include <stdint.h>

// Pines configurables
#define SH1106_I2C_PORT i2c0
#define SH1106_SDA_PIN 4
#define SH1106_SCL_PIN 5
#define SH1106_I2C_ADDR 0x3C

// Tamaño del display
#define SH1106_WIDTH 128
#define SH1106_HEIGHT 64
#define SH1106_BUFFERSIZE (SH1106_WIDTH * SH1106_HEIGHT / 8)

extern uint8_t sh1106_buffer[SH1106_BUFFERSIZE];

// Funciones públicas
void sh1106_init();
void sh1106_update();
void sh1106_clear();

void sh1106_draw_char(int x, int y, char c);
void sh1106_draw_text(int x, int y, const char *txt);

#endif
