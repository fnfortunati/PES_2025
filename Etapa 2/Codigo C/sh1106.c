#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/i2c.h"
#include "sh1106.h"
#include "font5x7.inc"

// Buffer de pantalla
uint8_t sh1106_buffer[SH1106_BUFFERSIZE];

// ---- Funciones internas ----
static void sh1106_send_cmd(uint8_t cmd) {
    uint8_t data[2] = {0x00, cmd};
    i2c_write_blocking(SH1106_I2C_PORT, SH1106_I2C_ADDR, data, 2, false);
}

static void sh1106_send_data(uint8_t data) {
    uint8_t buf[2] = {0x40, data};
    i2c_write_blocking(SH1106_I2C_PORT, SH1106_I2C_ADDR, buf, 2, false);
}

// ---- Inicializar OLED ----
void sh1106_init() {
    sleep_ms(50);

    sh1106_send_cmd(0xAE);
    sh1106_send_cmd(0xD5); sh1106_send_cmd(0x80);
    sh1106_send_cmd(0xA8); sh1106_send_cmd(0x3F);
    sh1106_send_cmd(0xD3); sh1106_send_cmd(0x00);
    sh1106_send_cmd(0x40);
    sh1106_send_cmd(0xAD); sh1106_send_cmd(0x8B);
    sh1106_send_cmd(0xA1);
    sh1106_send_cmd(0xC8);
    sh1106_send_cmd(0xDA); sh1106_send_cmd(0x12);
    sh1106_send_cmd(0x81); sh1106_send_cmd(0x7F);
    sh1106_send_cmd(0xD9); sh1106_send_cmd(0xF1);
    sh1106_send_cmd(0xDB); sh1106_send_cmd(0x40);
    sh1106_send_cmd(0xA4);
    sh1106_send_cmd(0xA6);
    sh1106_send_cmd(0xAF);

    sh1106_clear();
    sh1106_update();
}

// ---- Limpiar pantalla ----
void sh1106_clear() {
    for (int i = 0; i < SH1106_BUFFERSIZE; i++)
        sh1106_buffer[i] = 0x00;
}

// ---- Actualizar OLED ----
void sh1106_update() {
    for (uint8_t page = 0; page < 8; page++) {
        sh1106_send_cmd(0xB0 + page);
        sh1106_send_cmd(0x02);
        sh1106_send_cmd(0x10);

        for (uint8_t col = 0; col < 128; col++) {
            sh1106_send_data(sh1106_buffer[page * 128 + col]);
        }
    }
}

// ---- Dibujar un carácter ----
void sh1106_draw_char(int x, int y, char c) {
    if (c < 32 || c > 126) return;

    const uint8_t *glyph = font5x7[c - 32];

    for (int col = 0; col < 5; col++) {
        uint8_t column = glyph[col];
        int index = x + col + (y / 8) * 128;
        if (index >= 0 && index < SH1106_BUFFERSIZE)
            sh1106_buffer[index] = column;
    }
}

// ---- Dibujar texto ----
void sh1106_draw_text(int x, int y, const char *txt) {
    while (*txt) {
        sh1106_draw_char(x, y, *txt);
        x += 6;
        txt++;
    }
}
