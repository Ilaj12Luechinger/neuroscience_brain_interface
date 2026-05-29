import asyncio
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display, clear_output
from scipy import signal
from scipy.signal import welch
from idun_guardian_sdk import GuardianClient

# --- KONFIGURATION ---
MY_API_TOKEN = "idun_MWSQ4pkewAGNz8wwYzw_NsweXihLC8tIcFzah8vqqys4Nc-ALzjfTwl2"
fs = 250 
WINDOW_SECONDS = 5 
BUFFER_SIZE = fs * WINDOW_SECONDS

# --- DATA STORAGE ---
class LiveData:
    def __init__(self):
        self.timestamps = []
        self.ch1 = []
        self.is_running = True

live_buffer = LiveData()

# --- FILTER SETUP (wie in deinem Original-Code) ---
sos_bp = signal.butter(N=4, Wn=[1, 40], btype="bandpass", fs=fs, output="sos")
b_notch, a_notch = signal.iirnotch(50, Q=30, fs=fs)

# --- OPTIMIERTE FILTER FUNKTION ---
def apply_filters(data_array):
    if len(data_array) < fs:
        return data_array
    
    # Konvertierung zu float64, um Rechenfehler zu vermeiden
    data_array = np.asfarray(data_array)
    
    # 1. Echtzeit-Bandpass (sosfilt statt sosfiltfilt)
    # sosfilt hat weniger Latenz und ist performanter für Live-Daten
    filtered = signal.sosfilt(sos_bp, data_array)
    
    # 2. Notch Filter
    filtered = signal.filtfilt(b_notch, a_notch, filtered)
    
    # 3. DC Offset (Baseline) entfernen
    filtered = filtered - np.mean(filtered)
    
    return filtered

# --- KORRIGIERTE CALLBACK FUNKTION ---
def handle_live_data(event):
    if type(event).__name__ == "LiveInsightsEvent":
        if hasattr(event, 'message') and 'raw_eeg' in event.message:
            samples = event.message['raw_eeg']
            
            # Einmaliger Check für dich im Log, um das Format zu sehen:
            # print(f"DEBUG: Erstes Sample Format: {samples[0]}") 

            for sample in samples:
                # Extraktion des Wertes (Annahme: Key ist 'val')
                if isinstance(sample, dict):
                    val = sample.get('val', 0)
                else:
                    val = sample
                
                live_buffer.ch1.append(val)
                # Zeitstempel basierend auf Abtastrate
                live_buffer.timestamps.append(len(live_buffer.ch1) / fs)
            
            # Strengeres Buffer-Management für die Performance
            if len(live_buffer.ch1) > BUFFER_SIZE:
                live_buffer.ch1 = live_buffer.ch1[-BUFFER_SIZE:]
                live_buffer.timestamps = live_buffer.timestamps[-BUFFER_SIZE:]

# --- LIVE PLOT TASK ---
async def live_plot_task():
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    plt.ion() # Interaktiver Modus an
    
    while live_buffer.is_running:
        if len(live_buffer.ch1) >= BUFFER_SIZE:
            data = np.array(live_buffer.ch1)
            times = np.array(live_buffer.timestamps)
            
            filtered_data = apply_filters(data)
            
            # Plot Zeitbereich
            ax1.clear()
            ax1.plot(times, filtered_data, color='blue', linewidth=0.8)
            ax1.set_title("Live EEG (Real-time Filtered)")
            ax1.set_ylabel("Amplitude (µV)")
            ax1.grid(True, alpha=0.3)
            
            # Plot Frequenzbereich
            freqs, psd = welch(filtered_data, fs=fs, nperseg=fs*2)
            ax2.clear()
            ax2.semilogy(freqs, psd, color='red')
            ax2.set_xlim([0.5, 40])
            ax2.set_ylim([1e-2, 1e3])
            ax2.set_title("PSD (Welch)")
            ax2.set_xlabel("Frequency (Hz)")
            ax2.grid(True, which='both', alpha=0.3)
            
            clear_output(wait=True)
            display(fig)
        
        await asyncio.sleep(0.3) # Etwas schnelleres Update-Intervall
    plt.close(fig)

async def main():
    client = GuardianClient(api_token=MY_API_TOKEN, debug=False)
    
    # Subscribe
    client.subscribe_live_insights(raw_eeg=True, handler=handle_live_data)
    
    print("Verbindung wird aufgebaut...")
    
    # Starte den Plot-Task im Hintergrund
    plot_task = asyncio.create_task(live_plot_task())
    
    try:
        # Aufnahme starten
        await client.start_recording(recording_timer=600, led_sleep=False)
    except Exception as e:
        print(f"Fehler: {e}")
    finally:
        live_buffer.is_running = False
        await plot_task
        print("Aufnahme beendet.")

# Start
asyncio.run(main())