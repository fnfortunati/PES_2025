#include <math.h>
#include <stdint.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Intercambio bit-reversal
static void bit_reverse(float *real, float *imag, int n) {
    int j = 0;
    for (int i = 0; i < n; i++) {
        if (i < j) {
            float tr = real[i];
            float ti = imag[i];
            real[i] = real[j];
            imag[i] = imag[j];
            real[j] = tr;
            imag[j] = ti;
        }
        int m = n >> 1;
        while (m >= 1 && j >= m) {
            j -= m;
            m >>= 1;
        }
        j += m;
    }
}

// FFT radix-2
void fft_1024(float *real, float *imag) {
    int n = 1024*4;

    bit_reverse(real, imag, n);

    for (int len = 2; len <= n; len <<= 1) {
        float ang = -2 * M_PI / len;
        float wlen_r = cosf(ang);
        float wlen_i = sinf(ang);

        for (int i = 0; i < n; i += len) {
            float wr = 1.0f;
            float wi = 0.0f;

            for (int j = 0; j < len / 2; j++) {
                int i0 = i + j;
                int i1 = i + j + len/2;

                float u_r = real[i0];
                float u_i = imag[i0];

                float v_r = real[i1] * wr - imag[i1] * wi;
                float v_i = real[i1] * wi + imag[i1] * wr;

                real[i0] = u_r + v_r;
                imag[i0] = u_i + v_i;
                real[i1] = u_r - v_r;
                imag[i1] = u_i - v_i;

                float nxt_r = wr * wlen_r - wi * wlen_i;
                float nxt_i = wr * wlen_i + wi * wlen_r;
                wr = nxt_r;
                wi = nxt_i;
            }
        }
    }
}
