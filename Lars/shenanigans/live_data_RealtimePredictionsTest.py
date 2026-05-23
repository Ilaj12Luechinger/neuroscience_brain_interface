import asyncio
from idun_guardian_sdk import GuardianClient

# Konfiguration
RECORDING_TIMER: int = 60 * 5
MY_API_TOKEN = "idun_MWSQ4pkewAGNz8wwYzw_NsweXihLC8tIcFzah8vqqys4Nc-ALzjfTwl2"

def print_data(event):
    msg = event.message
    
    # 1. Behandle Realtime Predictions (Scores)
    if "predictionType" in msg:
        p_type = msg["predictionType"]
        result = msg.get("result", {})

        if p_type == "CALM_SCORE":
            score = result.get("relaxation_index_display", 0)
            print(f"🧘 [CALM] Score: {score:.2f}%")

        elif p_type == "COGNITIVE_READINESS":
            readiness = result.get("cognitive_readiness", 0)
            print(f"🧠 [READINESS] Score: {readiness:.2f}%")

        elif p_type == "QUALITY_SCORE":
            quality = result.get("quality_score", 0)
            print(f"📊 [QUALITY] Signalqualität: {quality:.2f}%")

        elif p_type == "BIN_HEOG":
            # Augenbewegungen (1 = erkannt, 0 = nichts)
            if result.get("heog") == 1:
                print("👀 [EYE] Augenbewegung erkannt!")

    # 2. Behandle IMU (Bewegung) - Optional
    # Falls du die IMU-Daten sehen willst, nimm die Raute vor der nächsten Zeile weg:
    # elif "imu" in msg and msg["imu"]:
    #    print(f"🏃 [MOTION] Bewegung erkannt (AccX: {msg['imu'][0]['acc_x']})")

async def main():
    client = GuardianClient(api_token=MY_API_TOKEN, debug=False)

    # Wir setzen IMU auf True, aber filtern es in print_data (oder setzen es auf False)
    client.subscribe_live_insights(
        raw_eeg=False, 
        filtered_eeg=False, 
        imu=True, 
        handler=print_data
    )

    client.subscribe_realtime_predictions(
        fft=False,
        jaw_clench=True,
        bin_heog=True,
        quality_score=True,
        calm_score=True,
        cognitive_readiness=True,
        hands_free_ui=True,
        handler=print_data
    )

    print("Verbindung wird hergestellt... Warte auf Daten-Streams...")
    await client.start_recording(recording_timer=RECORDING_TIMER)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBeendet.")