# Compilar MicroPython con ulab y FFT para Raspberry Pi Pico 2 en WSL

Este documento explica cómo compilar una versión personalizada de MicroPython para la **Raspberry Pi Pico 2 (RP2350)** utilizando **WSL (Ubuntu)**, incluyendo la librería `ulab` con soporte para FFT.

---

## ✅ 1. Preparar el entorno en WSL
Ejecuta estos comandos en tu terminal WSL (Ubuntu):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install git cmake build-essential python3 python3-pip -y
```

Instala el **toolchain ARM**:

```bash
sudo apt install gcc-arm-none-eabi libnewlib-arm-none-eabi -y
```

---

## ✅ 2. Clonar el repositorio oficial de MicroPython
```bash
cd ~
git clone https://github.com/micropython/micropython.git
cd micropython
git submodule update --init --recursive
```

Esto descarga MicroPython y sus submódulos (incluyendo `lib/ulab`).

---

## ✅ 3. Descargar el SDK de Raspberry Pi Pico
```bash
cd ports/rp2
git clone https://github.com/raspberrypi/pico-sdk.git
cd pico-sdk
git submodule update --init
```

Configura la variable de entorno para el SDK:
```bash
export PICO_SDK_PATH=$HOME/micropython/ports/rp2/pico-sdk
```

---

## ✅ 4. Activar `ulab` con FFT
Por defecto, `ulab` está incluido, pero algunas funciones pueden estar deshabilitadas. Vamos a asegurarnos:

- Abre el archivo:
  ```
  micropython/ports/rp2/mpconfigport.mk
  ```
- Verifica que esté esta línea:
  ```
  MICROPY_PY_ULAB = 1
  ```
- Luego, en:
  ```
  micropython/lib/ulab/code/ulab_fft.c
  ```
  Confirma que las funciones `fft` e `ifft` están habilitadas (normalmente lo están). Si no, habilítalas quitando cualquier `#if` que las excluya.

---

## ✅ 5. Compilar el firmware
Desde `ports/rp2`:

```bash
cd ~/micropython/ports/rp2
make submodules
make BOARD=PICO2
```

Esto generará un archivo `.uf2` en:
```
build-PICO2/firmware.uf2
```

---

## ✅ 6. Cargar el firmware en la Pico 2
- Conecta la Pico 2 en modo BOOTSEL (mantén presionado el botón BOOTSEL al conectar).
- Montará como un disco USB.
- Copia `firmware.uf2` a ese disco.

---

## ✅ 7. Verificar `ulab` y FFT
En el REPL de MicroPython:
```python
import ulab
from ulab import numpy as np

signal = np.array([1, 2, 3, 4, 5], dtype=np.float)
print(np.fft.fft(signal))
```

---