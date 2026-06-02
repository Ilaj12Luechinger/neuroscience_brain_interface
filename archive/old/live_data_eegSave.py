import asyncio
from idun_guardian_sdk import GuardianClient

# Konfiguration
RECORDING_TIMER: int = 60 * 5  # 5 Minuten Aufnahme
MY_API_TOKEN = "idun_MWSQ4pkewAGNz8wwYzw_NsweXihLC8tIcFzah8vqqys4Nc-ALzjfTwl2"

# Korrigierte Callback-Funktion
def print_data(event):
    # Wir nutzen type(event).__name__, um zu sehen, ob es ein 
    # LiveInsightsEvent oder ein RealtimePredictionEvent ist.
    event_type_name = type(event).__name__
    print(f"[{event_type_name}] -> {event.message}")

async def main():
    # Client initialisieren
    client = GuardianClient(api_token=MY_API_TOKEN, debug=False)

    # 1. Live Insights abonnieren (Rohdaten & IMU)
    client.subscribe_live_insights(
        raw_eeg=True, 
        filtered_eeg=False, 
        imu=False, 
        handler=print_data
    )

    # 2. Realtime Predictions abonnieren (Scores & Metriken)
    client.subscribe_realtime_predictions(
        fft=True,
        jaw_clench=False,
        bin_heog=False,
        quality_score=False,
        calm_score=False,
        cognitive_readiness=False,
        hands_free_ui=False,
        handler=print_data
    )

    print("Starte Verbindung zum Guardian Earbud...")
    
    # Aufnahme starten
    await client.start_recording(
        recording_timer=RECORDING_TIMER, 
        led_sleep=False, 
        calc_latency=False
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAufnahme durch Nutzer gestoppt.")
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")