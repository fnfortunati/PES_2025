import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading, queue, struct, binascii, serial, serial.tools.list_ports, csv
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

fs = 1024          # Frecuencia de muestreo por defecto (Hz)
HEADER = b'PICO'   # Cabecera del paquete binario recibido por UART


# Clase encargada de la lectura asíncrona del puerto serie

class SerialReader(threading.Thread):
    def __init__(self, ser, data_queue):
        super().__init__(daemon=True)
        self.ser = ser
        self.data_queue = data_queue
        self.running = True
        self.buffer = b''  # Buffer temporal para armar paquetes completos

    def run(self):
        #Hilo principal de lectura del puerto serie
        while self.running:
            try:
                data = self.ser.read(self.ser.in_waiting or 1)
                if data:
                    self.buffer += data
                    self._process_buffer()
            except Exception:
                break

    def _process_buffer(self):
        #Analiza el buffer, valida el CRC y extrae muestras + FFT + RMS + THD
        while True:
            header_index = self.buffer.find(HEADER)
            if header_index == -1 or len(self.buffer) < header_index + 4:
                return  # No hay encabezado completo
            self.buffer = self.buffer[header_index:]

            try:
                # Verifica que haya suficientes bytes para los campos fijos
                if len(self.buffer) < 4 + 4 + 2:
                    return

                # Decodificación del encabezado del paquete
                fs = struct.unpack_from('<I', self.buffer, 4)[0]
                n_samples = struct.unpack_from('<H', self.buffer, 8)[0]

                # Calcula posiciones de cada sección del paquete
                samples_start = 10
                samples_end = samples_start + n_samples * 2
                if len(self.buffer) < samples_end + 2:
                    return

                m_samples = struct.unpack_from('<H', self.buffer, samples_end)[0]
                fft_start = samples_end + 2
                fft_end = fft_start + m_samples * 8
                rms_start = fft_end
                thd_start = rms_start + 4
                crc_start = thd_start + 4
                expected_total_len = crc_start + 4

                if len(self.buffer) < expected_total_len:
                    return  # Paquete incompleto

                # Extrae el paquete completo
                payload = self.buffer[:expected_total_len]
                self.buffer = self.buffer[expected_total_len:]

                # --- Validación del CRC ---
                crc_recv = struct.unpack_from('<I', payload, crc_start)[0]
                crc_calc = binascii.crc32(payload[4:crc_start]) & 0xffffffff
                if crc_recv != crc_calc:
                    continue  # Se descarta si el CRC no coincide

                # --- Decodificación de los datos binarios ---
                samples = (np.frombuffer(payload[samples_start:samples_end], dtype=np.int16))/10
                fft_data = payload[fft_start:fft_end]
                fft_pairs = struct.iter_unpack('<ff', fft_data)
                freqs, amps = zip(*fft_pairs) if m_samples > 0 else ([], [])
                rms = struct.unpack_from('<f', payload, rms_start)[0]
                thd = struct.unpack_from('<f', payload, thd_start)[0]

                # Envía los datos procesados al hilo principal mediante la cola
                self.data_queue.put((samples, np.array(freqs), np.array(amps), rms, thd, fs))
            except Exception:
                return

    def stop(self):
        """Detiene el hilo de lectura"""
        self.running = False


# Clase principal de la aplicación (interfaz gráfica + lógica)

class PicoFFTApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PES - Etapa 2 - Fortunati / Martinez")
        self.data_queue = queue.Queue()    # Cola para recibir datos del hilo serie
        self.serial_thread = None
        self.ser = None
        self.connected = False
        self.paused = False

        # Variables de datos
        self.samples = np.array([])
        self.fft_freqs = np.array([])
        self.fft_amps = np.array([])
        self.rms = 0
        self.thd = 0
        self.annotation = None

        # Construcción de la UI
        self._build_ui()

        # Eventos de ventana y actualización periódica
        self.root.bind('<Configure>', self._on_resize)
        self.root.after(50, self.update_plot_loop)

    # Construcción de la interfaz gráfica
    
    def _build_ui(self):
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        # --- Barra superior con controles ---
        top_frame = ttk.Frame(self.root)
        top_frame.grid(row=0, column=0, sticky="ew")

        # Selección de puerto serie y botones de control
        self.port_cb = ttk.Combobox(top_frame, width=15)
        self.port_cb.grid(row=0, column=0)
        ttk.Button(top_frame, text="Refrescar", command=self._populate_ports).grid(row=0, column=1)
        self.connect_btn = ttk.Button(top_frame, text="Conectar", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=2)
        self.status_lbl = ttk.Label(top_frame, text="Desconectado", foreground="red")
        self.status_lbl.grid(row=0, column=3)
        self.pause_btn = ttk.Button(top_frame, text="Pausar", command=self.toggle_pause)
        self.pause_btn.grid(row=0, column=4)
        ttk.Button(top_frame, text="Guardar CSV", command=self.save_csv).grid(row=0, column=5)
        ttk.Button(top_frame, text="Limpiar", command=self.clear_graphs).grid(row=0, column=6)

        # Campo para enviar frecuencia al microcontrolador
        ttk.Label(top_frame, text="Frecuencia (Hz):").grid(row=0, column=7)
        self.freq_entry = ttk.Entry(top_frame, width=10)
        self.freq_entry.grid(row=0, column=8)
        ttk.Button(top_frame, text="Enviar Frecuencia", command=self.enviar_frecuencia).grid(row=0, column=9)

        # --- Frame para gráficos (señal y FFT) ---
        plot_frame = ttk.Frame(self.root)
        plot_frame.grid(row=1, column=0, sticky="nsew")
        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)

        # Figura con dos subgráficos
        self.fig = Figure(figsize=(6, 4), constrained_layout=True)
        self.ax_time = self.fig.add_subplot(211)
        self.ax_fft = self.fig.add_subplot(212)
        self.ax_time.set_title("Señal en el tiempo")
        self.ax_fft.set_title("FFT")
        self.ax_time.set_xlabel("Tiempo [ms]")
        self.ax_time.set_ylabel("Amplitud")
        self.ax_fft.set_xlabel("Frecuencia [Hz]")
        self.ax_fft.set_ylabel("Amplitud")

        # Inserta la figura en el GUI
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        # Barra de herramientas de Matplotlib
        toolbar_frame = ttk.Frame(self.root)
        toolbar_frame.grid(row=2, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()

        # Evento del mouse para mostrar info en el espectro
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

        # Carga inicial de los puertos disponibles
        self._populate_ports()

    # Funciones de comunicación serie
    
    def _populate_ports(self):
        #Actualiza la lista de puertos serie disponibles
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb['values'] = ports
        if ports:
            self.port_cb.current(0)

    def toggle_connection(self):
        #Conecta o desconecta el puerto serie
        if not self.connected:
            try:
                # Apertura del puerto serie
                self.ser = serial.Serial(self.port_cb.get(), 115200, timeout=1)
                self.serial_thread = SerialReader(self.ser, self.data_queue)
                self.serial_thread.start()
                self.connected = True
                self.status_lbl.config(text="Conectado", foreground="green")
                self.connect_btn.config(text="Desconectar")
            except Exception as e:
                messagebox.showerror("Error", str(e))
        else:
            # Cierre ordenado de la conexión
            if self.serial_thread:
                self.serial_thread.stop()
            if self.ser:
                self.ser.close()
            self.connected = False
            self.status_lbl.config(text="Desconectado", foreground="red")
            self.connect_btn.config(text="Conectar")

    def enviar_frecuencia(self):
        #Envía una frecuencia al microcontrolador vía UART (ajustada a potencia de 2)
        if not self.connected or not self.ser:
            messagebox.showwarning("Aviso", "Debe conectar primero el dispositivo.")
            return
        try:
            frecuencia = int(self.freq_entry.get())
            if frecuencia <= 0:
                messagebox.showerror("Error", "La frecuencia debe ser mayor que 0.")
                return

            # Ajuste a la potencia de 2 más cercana
            potencia = round(math.log2(frecuencia))
            frecuencia_corregida = 2 ** potencia

            # Envío binario (4 bytes, formato little-endian)
            data = struct.pack('<I', frecuencia_corregida)
            self.ser.write(data)

            messagebox.showinfo("Éxito",
                                f"Frecuencia corregida enviada: {frecuencia_corregida} Hz "
                                f"(original: {frecuencia} Hz)")
        except ValueError:
            messagebox.showerror("Error", "Ingrese un valor numérico válido.")

    
    # Funciones de control y gráficos
    
    def toggle_pause(self):
        #Pausa o reanuda la actualización de los gráficos
        self.paused = not self.paused
        self.pause_btn.config(text="Continuar" if self.paused else "Pausar")

    def save_csv(self):
        #Guarda los datos de señal y FFT en un archivo CSV
        if self.samples.size == 0:
            messagebox.showwarning("Aviso", "No hay datos para guardar")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv")
        if file_path:
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Muestras"])
                writer.writerow(self.samples.tolist())
                writer.writerow(["Frecuencia", "Amplitud"])
                for freq, amp in zip(self.fft_freqs, self.fft_amps):
                    writer.writerow([freq, amp])
            messagebox.showinfo("Éxito", "Datos guardados en CSV")

    def clear_graphs(self):
        #Limpia los gráficos y reinicia las variables
        self.samples = np.array([])
        self.fft_freqs = np.array([])
        self.fft_amps = np.array([])
        self.rms = 0
        self.thd = 0
        self.ax_time.cla()
        self.ax_fft.cla()
        self.ax_time.set_title("Señal en el tiempo")
        self.ax_fft.set_title("FFT")
        self.canvas.draw()

    def update_plot_loop(self):
        #Bucle periódico que actualiza los gráficos con los datos recibidos
        if not self.paused and not self.data_queue.empty():
            self.samples, self.fft_freqs, self.fft_amps, self.rms, self.thd, self.fs = self.data_queue.get()
            self._redraw_plots()
        self.root.after(200, self.update_plot_loop)

    def _redraw_plots(self):
        #Actualiza los gráficos de tiempo y FFT con los nuevos datos
        if hasattr(self, 'fs') and self.fs > 0:
            t = (np.arange(len(self.samples)) / self.fs) * 1000
        else:
            t = np.arange(len(self.samples))

        self.ax_time.cla()
        self.ax_fft.cla()

        # Gráfico de la señal
        self.ax_time.plot(t, self.samples, color='blue')
        self.ax_time.set_xlim(0, 100)
        #self.ax_time.set_xlim(t[0], t[-1])
        self.ax_time.set_ylim(min(self.samples) * 1.1,
                              max(self.samples) * 1.1 if max(self.samples) > 0 else 1)
        self.ax_time.set_title(f"Señal - RMS: {self.rms:.2f}")
        self.ax_time.set_xlabel("Tiempo [ms]")
        self.ax_time.set_ylabel("Amplitud")

        # Gráfico del espectro FFT
        self.fft_bar = self.ax_fft.bar(self.fft_freqs, self.fft_amps, color='orange')
        self.ax_fft.set_xlim(0, max(self.fft_freqs) * 1.05 if self.fft_freqs.size > 0 else 1)
        self.ax_fft.set_ylim(0, max(self.fft_amps) * 1.2 if self.fft_amps.size > 0 else 1)
        self.ax_fft.set_title(f"FFT - THD: {self.thd :.2f}%")
        self.ax_fft.set_xlabel("Frecuencia [Hz]")
        self.ax_fft.set_ylabel("Amplitud")

        self.canvas.draw()

    # Eventos de interfaz y visualización
    
    def _on_resize(self, event):
        #Redibuja la figura al cambiar el tamaño de la ventana
        if hasattr(self, '_resize_pending') and self._resize_pending:
            return
        self._resize_pending = True
        self.root.after(300, self._perform_resize)

    def _perform_resize(self):
        self._resize_pending = False
        self.canvas.draw()

    def _on_mouse_move(self, event):
        #Muestra información de frecuencia y amplitud al pasar el mouse sobre la FFT
        if event.inaxes == self.ax_fft and self.fft_freqs.size > 0:
            x = event.xdata
            if x is None:
                return
            idx = (np.abs(self.fft_freqs - x)).argmin()
            freq = self.fft_freqs[idx]
            amp = self.fft_amps[idx]

            # Quita la anotación anterior
            if self.annotation:
                self.annotation.set_visible(False)

            # Crea una nueva anotación cerca del punto
            self.annotation = self.ax_fft.annotate(
                f"Freq: {freq:.2f} Hz\nAmp: {amp:.4f}",
                xy=(freq, amp),
                xytext=(freq, amp + max(self.fft_amps) * 0.1),
                arrowprops=dict(facecolor='black', shrink=0.05),
                bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.7)
            )
            self.canvas.draw()

# Punto de entrada del programa

if __name__ == "__main__":
    root = tk.Tk()
    app = PicoFFTApp(root)
    root.mainloop()
