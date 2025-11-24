from ulab import numpy as np
from machine import UART, Pin, ADC, Timer, I2C
import struct, binascii, time
from sh1106 import SH1106_I2C

# --- Configuración OLED ---
WIDTH, HEIGHT = 128, 64
i2c = I2C(0, scl=Pin(9), sda=Pin(8), freq=100000)
oled = SH1106_I2C(WIDTH, HEIGHT, i2c)
oled_enabled = True

# --- UART ---
uart = UART(1, baudrate=115200, tx=Pin(4), rx=Pin(5))

# --- ADC ---
adc = ADC(Pin(26))

# --- Parámetros ---
fs = 1024
N = 1024
HEADER = b'PICO'

# =====================================================
#   DETECCIÓN DE CRUCE POR CERO ASCENDENTE (VCC/2)
# =====================================================
def esperar_cruce_cero():
    UMBRAL = 1.65   # Punto medio VCC/2
    prev = (adc.read_u16() * 3.3) / 65535

    while True:
        actual = (adc.read_u16() * 3.3) / 65535

        # Cruce ascendente: antes abajo del medio y ahora arriba
        if prev < UMBRAL and actual >= UMBRAL:
            return

        prev = actual
        time.sleep_us(50)   # Lectura rápida


# --- Función recepción frecuencia de muestreo ---
def recibir_fs():
    global fs
    if uart.any() >= 4:
        data = uart.read(4)
        if data and len(data) == 4:
            new_fs = struct.unpack('<I', data)[0]
            if 10 <= new_fs <= 20000:
                fs = new_fs
                print("Nueva frecuencia de muestreo:", fs)
                if fs > 10000:
                    print("Advertencia: fs demasiado alta, ajustando a 10000 Hz")
                    fs = 10000
            else:
                print("Frecuencia fuera de rango:", new_fs)


# =====================================================
#                MUESTREO SINCRONIZADO
# =====================================================
def muestrear():
    signal = []
    sampling_done = False
    start_time = time.ticks_ms()

    # ---------- Esperar cruce por cero ----------
    esperar_cruce_cero()

    def sample_adc(timer):
        nonlocal signal, sampling_done
        if len(signal) < N:
            val = ((adc.read_u16() * 3.3) / 65535)
            signal.append(val)
        else:
            timer.deinit()
            sampling_done = True

    timer = Timer()
    timer.init(freq=fs, mode=Timer.PERIODIC, callback=sample_adc)

    while not sampling_done:
        time.sleep_ms(1)
        if time.ticks_diff(time.ticks_ms(), start_time) > 5000:
            print("Error: muestreo no completado en tiempo esperado")
            timer.deinit()
            return None

    return np.array(signal)


# =====================================================
#                PROCESAMIENTO FFT + ARMÓNICOS
# =====================================================
def procesar(signal):
    signal = signal - np.mean(signal)

    #Ventana de Hanning
    n = np.arange(N)
    window = 0.5 - 0.5 * np.cos(2 * np.pi * n / (N - 1))
    signal_windowed = signal * window
    correction_factor = 1 / (np.sum(window) / N)

    #Calculo de la FFT
    spectrum = np.fft.fft(signal_windowed)
    frequencies = np.linspace(0, fs, N)
    magnitudes = np.sqrt(spectrum.real**2 + spectrum.imag**2)
    amplitudes = correction_factor * (2 / N) * magnitudes

    freqs_pos = frequencies[:N//2]
    amplitudes_pos = amplitudes[:N//2]

    # Pico detection
    umbral = 0.01 * np.max(amplitudes_pos)
    armonicos = []

    for i in range(1, len(amplitudes_pos) - 1):
        if (amplitudes_pos[i] > amplitudes_pos[i - 1] and
            amplitudes_pos[i] > amplitudes_pos[i + 1] and
            amplitudes_pos[i] > umbral):
            armonicos.append((freqs_pos[i], amplitudes_pos[i]))

    if len(armonicos) > 0:
        armonicos.sort(key=lambda x: x[1], reverse=True)
        f1, a1 = armonicos[0]
    else:
        f1, a1 = 0.0, 0.0

    #Calculo de TRMS
    Vrms = np.sqrt(np.mean(signal ** 2))

    #Filtro los primeros 10 armonicos reales
    arm_temp = []

    for fr, a in armonicos:
        if f1 <= 0:
            continue

        n = round(fr / f1)
        if 1 <= n <= 10:
            if abs(fr - n*f1) <= f1 * 0.10:  # tolerancia 10%
                arm_temp.append((n, fr, a))

    arm_temp.sort(key=lambda x: x[0])
    armonicos_ordenados = [(fr, a) for (n, fr, a) in arm_temp[:10]]

    # THD con los 10 armónicos
    suma = 0
    for fr, a in armonicos_ordenados[1:]:
        suma += a*a
    THD = (np.sqrt(suma) / (a1 + 1e-12)) * 100

    return armonicos_ordenados, Vrms, THD, f1


# --- Imprimir resultados ---
def imprimir(armonicos_ordenados, Vrms, THD, f1):
    print("\n===============================")
    print(f"Frecuencia fundamental: {f1:.0f} Hz")
    print(f"Vrms: {Vrms:.3f} V")
    print(f"THD: {THD:.2f} %")
    print("-------------------------------")
    print("ARMÓNICOS (max 10):")
    for i, (fr, a) in enumerate(armonicos_ordenados):
        print(f"{i+1:>2d}: {fr:>9.0f} Hz   {a:>9.4f} V")


# --- Enviar trama ---
def enviar_trama(signal, armonicos_ordenados, Vrms, THD):
    try:
        frame = bytearray()
        frame.extend(HEADER)
        
        # Frecuencia de muestreo
        frame.extend(struct.pack('<I', fs))
        
        # Número de muestras
        frame.extend(struct.pack('<H', N))

        # Muestras en int16
        samples_int16 = [max(min(int((v / 3.3) * 32767), 32767), -32767) for v in signal]
        for s in samples_int16:
            frame.extend(struct.pack('<h', s))

        # Armónicos
        M = len(armonicos_ordenados)
        frame.extend(struct.pack('<H', M))
        for f, a in armonicos_ordenados:
            frame.extend(struct.pack('<ff', f, a))

        # RMS y THD
        frame.extend(struct.pack('<f', Vrms))
        frame.extend(struct.pack('<f', THD))

        # Calcular CRC desde el byte 4 en adelante
        crc = binascii.crc32(frame[4:]) & 0xFFFFFFFF
        frame.extend(struct.pack('<I', crc))

        MAX_CHUNK = 512  # Tamaño seguro por bloque
        if len(frame) > MAX_CHUNK:
            print("Enviando trama en bloques...")
            for i in range(0, len(frame), MAX_CHUNK):
                uart.write(frame[i:i+MAX_CHUNK])
                time.sleep_ms(10)  # Pequeña pausa para evitar saturación
        else:
            uart.write(frame)
            
    except Exception as e:
        print("Error en enviar_trama:", e)


# --- OLED ---
def OLED(f1, Vrms, THD):
    oled.fill(0)
    oled.text("f1={:.0f}Hz".format(f1), 0, 0)
    oled.text("Vrms={:.3f}V".format(Vrms), 0, 20)
    oled.text("THD={:.2f}%".format(THD), 0, 40)
    oled.show()


# =====================================================
#                 BUCLE PRINCIPAL
# =====================================================
while True:
    recibir_fs()
    
    signal = muestrear()
    if signal is None:
        continue
        
    armonicos, Vrms, THD, f1 = procesar(signal)
    imprimir(armonicos, Vrms, THD, f1)
    OLED(f1, Vrms, THD)
    enviar_trama((signal-1.65), armonicos, Vrms, THD)
    
    time.sleep(2)
