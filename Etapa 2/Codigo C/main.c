#include <stdio.h>
#include <math.h>
#include "pico/stdlib.h"
#include "hardware/adc.h"
#include "hardware/dma.h"
#include "fft.h"
#include "hardware/i2c.h"
#include "sh1106.h"

#define SAMPLES   4096
#define NFFT      4096

// 1 Hz resolución
#define FS        4096.0f   

// ADC
#define VREF      3.25f
#define ADC_MAX   4095.0f
#define ADC_OFFSET 2048     

// Ventana HANN
#define HANN_GAIN 0.6123f      // Ganancia coherente para correccion de la vrms

uint16_t buffer[SAMPLES];
float real_fft[NFFT];
float imag_fft[NFFT];
float magnitude[NFFT];

int main() {
    stdio_init_all();
    sleep_ms(300);

    // I2C + OLED
    i2c_init(i2c0, 400000);
    gpio_set_function(8, GPIO_FUNC_I2C);
    gpio_set_function(9, GPIO_FUNC_I2C);
    gpio_pull_up(8);
    gpio_pull_up(9);
    sh1106_init(i2c0);

    // ADC
    adc_init();
    adc_gpio_init(26);
    adc_select_input(0);

    adc_fifo_setup(true, true, 1, false, false);
    adc_set_clkdiv(11718.75f);   // 1024 Hz exacto // FS = 48 MHz / clkdiv  → clkdiv = 46875 para 1024 Hz

    // DMA
    int chan = dma_claim_unused_channel(true);
    dma_channel_config cfg = dma_channel_get_default_config(chan);
    channel_config_set_transfer_data_size(&cfg, DMA_SIZE_16);
    channel_config_set_read_increment(&cfg, false);
    channel_config_set_write_increment(&cfg, true);
    channel_config_set_dreq(&cfg, DREQ_ADC);

    while (true) {

        // DMA start
        dma_channel_configure(chan, &cfg, buffer, &adc_hw->fifo, SAMPLES, false);
        adc_fifo_drain();
        adc_run(true);
        dma_channel_start(chan);
        dma_channel_wait_for_finish_blocking(chan);
        adc_run(false);

        // ============================
        // PREPARAR DATOS + VENTANA HANN
        // ============================
        for (int i = 0; i < SAMPLES; i++) {

            float centered = (float)((int)buffer[i] - ADC_OFFSET);

            float hann = 0.5f * (1.0f - cosf((2.0f * M_PI * i) / (SAMPLES - 1)));

            real_fft[i] = centered * hann;
            imag_fft[i] = 0.0f;
        }

        // FFT
        fft_1024(real_fft, imag_fft);

        // Magnitudes FFT
        for (int i = 0; i < NFFT/2; i++) {
            magnitude[i] = sqrtf(real_fft[i]*real_fft[i] + imag_fft[i]*imag_fft[i]);
        }

        // ============================
        // FRECUENCIA FUNDAMENTAL
        // ============================
        int f0_idx = 1;
        float max_val = magnitude[1];

        for (int i = 2; i < FS/2; i++) {
            if (magnitude[i] > max_val) {
                max_val = magnitude[i];
                f0_idx = i;
            }
        }

        float f0 = (FS * f0_idx) / NFFT;

        printf("\n===============================\n");
        printf("FRECUENCIA DETECTADA: %.2f Hz\n", f0);
        printf("===============================\n");

        // ============================
        // ARMÓNICOS + THD + VRMS
        // ============================

        float fundamental_rms = 0;
        float sum_harm_sq = 0;
        float total_rms_sq = 0;

        printf("\n=== ARMÓNICOS (1–20) ===\n");

        for (int n = 1; n <= 20; n++) {

            float f_h = n * f0;
            int idx = (int)roundf(f_h * NFFT / FS);

            if (idx >= NFFT/2) continue;

            float vrms_adc =
                (magnitude[idx] / (NFFT/2)) / 1.4142f *
                (1.0f / HANN_GAIN);       // CORRECCIÓN HANN

            float mv = (vrms_adc * VREF / ADC_MAX) * 1000.0f;

            printf("Armónico %d: %.1f Hz → %.2f mV RMS\n", n, f_h, mv);

            if (n == 1) fundamental_rms = vrms_adc;
            else sum_harm_sq += vrms_adc * vrms_adc;
        }

        // RMS TOTAL CORREGIDO
        for (int i = 1; i < NFFT/2; i++) {

            float vrms =
                (magnitude[i] / (NFFT/2)) / 1.4142f *
                (1.0f / HANN_GAIN);   // CORRECCIÓN

            total_rms_sq += vrms * vrms;
        }

        float total_rms = sqrtf(total_rms_sq);
        float total_mv = (total_rms * VREF / ADC_MAX) * 1000.0f;

        // THD
        float thd = sqrtf(sum_harm_sq) / fundamental_rms;
        float thd_percent = thd * 100.0f;

        printf("\n===============================\n");
        printf("VRMS TOTAL: %.2f mV\n", total_mv);
        printf("THD: %.4f  (%.2f %%)\n", thd, thd_percent);
        printf("===============================\n");

        // OLED
        sh1106_clear();

        char buf[32];

        sh1106_draw_text(0, 10, "Fr0:");
        sprintf(buf, "%.1f Hz", f0);
        sh1106_draw_text(35, 10, buf);

        sprintf(buf, "Vrms: %.0f mV", total_mv);
        sh1106_draw_text(0, 25, buf);

        sprintf(buf, "THD: %.2f %%", thd_percent);
        sh1106_draw_text(0, 40, buf);

        sh1106_update(i2c0);

        sleep_ms(300);
    }
}
