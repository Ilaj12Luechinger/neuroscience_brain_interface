import asyncio
import csv
import json
import os
from idun_guardian_sdk import GuardianClient

# Konfiguration
MY_API_TOKEN = "idun_MWSQ4pkewAGNz8wwYzw_NsweXihLC8tIcFzah8vqqys4Nc-ALzjfTwl2"
CSV_FILENAME = "idun_fft_full_report.csv"

def init_csv():
    if not os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, mode='w', newline='') as f:
            writer = csv.writer(f)
            # Wir speichern Zeitstempel und die FFT-Leistungswerte
            writer.writerow(["Timestamp", "Delta", "Theta", "Alpha", "Beta", "Full_FFT_JSON"])

def handle_data_silent(event):
    msg = event.message
    event_type_name = type(event).__name__

    if event_type_name == "RealtimePredictionEvent" and msg.get("predictionType") == "FFT":
        result = msg.get("result", {})
        ts = result.get("timestamp", "N/A")
        fft_values = result.get("fft", [])

        # Falls die Liste leer ist, geben wir eine kurze Info aus und überspringen den Rest
        if not fft_values:
            print(f"⏳ {ts} | Warte auf stabile FFT-Berechnung (Liste noch leer)...")
            return

        # Frequenzbereiche definieren (Mittelwerte berechnen für bessere Übersicht)
        # Wir nutzen slicing [start:stop]
        def get_avg(start, stop):
            vals = fft_values[start:stop]
            return sum(vals) / len(vals) if vals else 0

        delta = get_avg(1, 4)   # 1-4 Hz
        theta = get_avg(4, 8)   # 4-8 Hz
        alpha = get_avg(8, 13)  # 8-13 Hz
        beta  = get_avg(13, 30) # 13-30 Hz

        # Schöne Ausgabe in der Konsole
        print("-" * 50)
        print(f"⏱️ Zeit: {ts}")
        print(f"🌊 Delta (Tiefschlaf): {delta:.2f}")
        print(f"🧘 Theta (Traum/Entspannung): {theta:.2f}")
        print(f"✨ Alpha (Ruhe/Fokus): {alpha:.2f}")
        print(f"⚡ Beta (Aktivität): {beta:.2f}")
        print("-" * 50)

        # In CSV speichern
        with open(CSV_FILENAME, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([ts, delta, theta, alpha, beta, json.dumps(fft_values)])

async def main():
    init_csv()
    client = GuardianClient(api_token=MY_API_TOKEN, debug=False)

    # Wir brauchen raw_eeg als Basis für die FFT
    client.subscribe_live_insights(raw_eeg=True, handler=handle_data_silent)
    
    # FFT abonnieren
    client.subscribe_realtime_predictions(fft=True, handler=handle_data_silent)

    print("📡 Suche Earbud und starte Stream... Bitte ruhig halten für bessere Qualität.")
    await client.start_recording(recording_timer=60*15)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAufnahme gestoppt.")