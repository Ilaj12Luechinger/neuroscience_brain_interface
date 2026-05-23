"""
Sample script for using the Guardian Earbud Client

- Start recording data from the Guardian Earbuds
"""

import asyncio
from idun_guardian_sdk import GuardianClient

RECORDING_TIMER: int = 60 * 3  # 3 minutes of recording
LED_SLEEP: bool = False

my_api_token = "idun_MWSQ4pkewAGNz8wwYzw_NsweXihLC8tIcFzah8vqqys4Nc-ALzjfTwl2"


# Example callback function
def print_data(event):
    print("CB Func:", event.message)


if __name__ == "__main__":
    client = GuardianClient(api_token=my_api_token, debug=True)

    # Subscribe to live insights and/or realtime predictions
    client.subscribe_live_insights(raw_eeg=True, filtered_eeg=True, handler=print_data)
    client.subscribe_realtime_predictions(fft=True, jaw_clench=False, handler=print_data)

    # start a recording session
    asyncio.run(
        client.start_recording(
            recording_timer=RECORDING_TIMER, led_sleep=LED_SLEEP, calc_latency=False
        )
    )