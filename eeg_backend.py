import asyncio
import argparse
import os
import json
from pathlib import Path
import numpy as np
import pandas as pd
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from scipy import signal
from scipy.signal import welch
from scipy.integrate import trapezoid

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from idun_guardian_sdk import GuardianClient
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

def parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

parser = argparse.ArgumentParser(description="EEG backend for live or offline processing.")
parser.add_argument("--mode", choices=["live", "offline"], default="live")
parser.add_argument("--device-address", default="E0:53:73:AB:F9:05")
parser.add_argument(
    "--csv-file",
    default=str(_SCRIPT_DIR / "offline_data_analysis" / "livedata_test.csv"),
)
parser.add_argument("--use-iaf", type=parse_bool, default=True)
parser.add_argument("--calibration-seconds", type=float, default=5.0)
parser.add_argument("--playback-speed", type=float, default=10.0)
parser.add_argument("--recording-duration", type=int, default=0)
parser.add_argument("--api-token", default="idun_MWSQ4pkewAGNz8wwYzw_NsweXihLC8tIcFzah8vqqys4Nc-ALzjfTwl2")
args = parser.parse_args()

MODE = args.mode
fs = 250
WINDOW_SECONDS = 6
BUFFER_SIZE = fs * WINDOW_SECONDS

USE_IAF = args.use_iaf
IAF_MIN = 8.5
IAF_MAX = 12.5

CALIBRATION_SECONDS = float(args.calibration_seconds)

BANDS = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 12),
    "beta": (12, 30),
    "gamma": (30, 40),
}

CSV_FILE = args.csv_file
PLAYBACK_SPEED = float(args.playback_speed)
CHUNK_SIZE = 50

MY_API_TOKEN = args.api_token
DEVICE_ADDRESS = args.device_address
RECORDING_DURATION = args.recording_duration if args.recording_duration and args.recording_duration > 0 else None

SMOOTHING_ALPHA = 0.08
STATE_MIN_SECONDS = 2.0
RELAX_BOOST = 0.0
FOCUSED_BOOST = 0.0
UPDATE_INTERVAL = 0.1

try:
    _SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    _SCRIPT_DIR = Path.cwd()

OVERLAY_STATE_FILE = _SCRIPT_DIR / "lofilia_state.txt"
_overlay_write_failed = False
_last_overlay_payload = None

def _state_payload(state: str, current_t: float = 0.0) -> dict:
    calib_progress = min(1.0, current_t / CALIBRATION_SECONDS) if not calibration.complete else 1.0
    payload = {
        "state": state,
        "time_since_state_change": round(current_t - _last_state_time, 2) if (_last_state_time is not None and _start_time is not None) else 0.0,
        "calibration_progress": round(calib_progress, 3),
        "calibration_seconds": CALIBRATION_SECONDS,
        "iaf": calibration.iaf,
        "engagement": float(_smoothed["engagement"]) if _smoothed["engagement"] is not None else None,
        "relaxation": float(_smoothed["relaxation"]) if _smoothed["relaxation"] is not None else None,
        "theta_baseline": float(calibration.theta_baseline) if calibration.theta_baseline is not None else None,
        "paf": calibration.paf,
        "cog": calibration.cog,
        "complete": bool(calibration.complete),
    }
    return payload

def write_overlay_state(state: str, current_t: float = 0.0):
    """Write the current state for lofilia.py using an atomic file replace."""
    global _overlay_write_failed, _last_overlay_payload
    try:
        payload = _state_payload(state, current_t)
        # Re-write if file missing even if payload unchanged
        if payload == _last_overlay_payload and OVERLAY_STATE_FILE.exists():
            return
        # Write directly — avoids OneDrive locking the .tmp file during atomic rename
        OVERLAY_STATE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _last_overlay_payload = payload
        if _overlay_write_failed:
            # Reset flag if write succeeds after a previous failure
            globals()["_overlay_write_failed"] = False
    except Exception as exc:
        if not _overlay_write_failed:
            print(f"WARNING: could not write overlay state file {OVERLAY_STATE_FILE}: {exc}")
            _overlay_write_failed = True

_executor = ThreadPoolExecutor(max_workers=2)

sos_bp = signal.butter(N=4, Wn=[1, 40], btype="bandpass", fs=fs, output="sos")
b_notch, a_notch = signal.iirnotch(50, Q=30, fs=fs)

_zi_bp = signal.sosfilt_zi(sos_bp) * 0
_zi_notch = signal.lfilter_zi(b_notch, a_notch) * 0

nperseg = fs * (WINDOW_SECONDS // 2)
noverlap = nperseg // 2

def apply_filters(data: np.ndarray) -> np.ndarray:
    global _zi_bp, _zi_notch
    data = np.asarray(data, dtype=float)
    if len(data) < 50:
        return data
    filtered, _zi_notch = signal.lfilter(b_notch, a_notch, data, zi=_zi_notch)
    filtered, _zi_bp = signal.sosfilt(sos_bp, filtered, zi=_zi_bp)
    return filtered - np.mean(filtered)

def reset_filter_state():
    global _zi_bp, _zi_notch
    _zi_bp = signal.sosfilt_zi(sos_bp) * 0
    _zi_notch = signal.lfilter_zi(b_notch, a_notch) * 0

def _welch_only(filtered: np.ndarray):
    if len(filtered) < nperseg:
        return None, None
    freqs, psd = welch(
        filtered,
        fs=fs,
        nperseg=nperseg,
        noverlap=noverlap,
        window="hann",
        scaling="density",
    )
    return freqs, psd

def band_power(freqs: np.ndarray, psd: np.ndarray, band: tuple) -> float:
    idx = (freqs >= band[0]) & (freqs <= band[1])
    return float(trapezoid(psd[idx], freqs[idx])) if np.any(idx) else 0.0

def compute_features(freqs: np.ndarray, psd: np.ndarray, theta_baseline: float) -> dict:
    eps = 1e-8
    theta = band_power(freqs, psd, BANDS["theta"])
    alpha = band_power(freqs, psd, BANDS["alpha"])
    beta = band_power(freqs, psd, BANDS["beta"])
    theta_dev = theta - theta_baseline
    eng_denom = max(alpha + theta_dev, theta_baseline * 0.1 + eps)
    return {
        "engagement": beta / eng_denom,
        "relaxation": alpha / (beta + eps),
        "_theta": theta,
        "_alpha": alpha,
        "_beta": beta,
    }

class LiveData:
    def __init__(self):
        self.timestamps = deque(maxlen=BUFFER_SIZE)
        self.ch1 = deque(maxlen=BUFFER_SIZE)
        self.is_running = True

live_buffer = LiveData()

class Calibration:
    def __init__(self):
        self._raw = []
        self._psds = []
        self._freqs = None
        self.theta_baseline = 1e-8
        self.iaf = None
        self.avg_psd = None
        self.paf = None
        self.cog = None
        self.end_time = None
        self.complete = False

    def add_sample(self, features: dict):
        self._raw.append({k: features[k] for k in ("_theta", "_alpha", "_beta")})

    def add_psd(self, freqs: np.ndarray, psd: np.ndarray):
        if self._freqs is None:
            self._freqs = freqs
        self._psds.append(psd)

    def finalize(self):
        thetas = np.array([s["_theta"] for s in self._raw])
        self.theta_baseline = float(np.mean(thetas)) or 1e-8

        if USE_IAF and self._psds and self._freqs is not None:
            avg_psd = np.mean(self._psds, axis=0)
            mask = (self._freqs >= 7) & (self._freqs <= 13)
            fa, pa = self._freqs[mask], avg_psd[mask]
            if len(fa) > 0 and pa.sum() > 0:
                iaf = float(fa[np.argmax(pa)])
                if IAF_MIN <= iaf <= IAF_MAX:
                    self.iaf = iaf
                    BANDS["theta"] = (4.0, round(iaf - 2, 2))
                    BANDS["alpha"] = (round(iaf - 2, 2), round(iaf + 2, 2))
                    BANDS["beta"] = (round(iaf + 2, 2), 30.0)
                else:
                    print(
                        f"IAF candidate {iaf:.2f} Hz outside valid range "
                        f"({IAF_MIN}-{IAF_MAX} Hz) -- using standard bands"
                    )

        if self._psds and self._freqs is not None:
            self.avg_psd = np.mean(self._psds, axis=0)
            mask_wide = (self._freqs >= 7) & (self._freqs <= 13)
            fw, pw = self._freqs[mask_wide], self.avg_psd[mask_wide]
            if len(fw) > 0 and pw.sum() > 0:
                self.paf = float(fw[np.argmax(pw)])
                self.cog = float(np.sum(fw * pw) / np.sum(pw))

        self.complete = True

calibration = Calibration()

def reset_state():
    """Reset all session state so main() can be re-run without a kernel restart."""
    global calibration, _smoothed, _dwell_candidate, _dwell_count
    global _confirmed_state, _dwell_frames_cached, _last_overlay_payload

    calibration = Calibration()

    BANDS["theta"] = (4.0, 8.0)
    BANDS["alpha"] = (8.0, 12.0)
    BANDS["beta"] = (12.0, 30.0)

    for k in _smoothed:
        _smoothed[k] = None

    _dwell_candidate = None
    _dwell_count = 0
    _confirmed_state = "CALIBRATING"
    _dwell_frames_cached = max(1, int(STATE_MIN_SECONDS / UPDATE_INTERVAL))
    _last_overlay_payload = None

_smoothed = {"engagement": None, "relaxation": None}

def smooth_features(raw: dict) -> dict:
    for key in _smoothed:
        if _smoothed[key] is None:
            _smoothed[key] = raw[key]
        else:
            _smoothed[key] = (SMOOTHING_ALPHA * raw[key] + (1 - SMOOTHING_ALPHA) * _smoothed[key])
    return dict(_smoothed)

_KEY_TO_STATE = {
    "engagement": "FOCUSED",
    "relaxation": "DRIFTING",
}

_dwell_candidate = None
_dwell_count = 0
_confirmed_state = "CALIBRATING"
_dwell_frames_cached = max(1, int(2.0 / 0.1))

def _update_dwell_cache():
    global _dwell_frames_cached
    _dwell_frames_cached = max(1, int(STATE_MIN_SECONDS / UPDATE_INTERVAL))

def classify(smooth: dict) -> str:
    scores = {
        "engagement": smooth["engagement"] + FOCUSED_BOOST,
        "relaxation": smooth["relaxation"] + RELAX_BOOST,
    }
    global _dwell_candidate, _dwell_count, _confirmed_state
    candidate = _KEY_TO_STATE[max(
        ("engagement", "relaxation"),
        key=lambda k: scores[k]
    )]
    if candidate == _dwell_candidate:
        _dwell_count += 1
    else:
        _dwell_candidate = candidate
        _dwell_count = 1
    if _dwell_count >= _dwell_frames_cached:
        _confirmed_state = candidate
    return _confirmed_state

_start_time = None
_dirty = False
_last_state = None
_last_state_time = None

def handle_live_data(event):
    global _dirty
    if isinstance(event, dict):
        msg = event.get("message", {})
    else:
        msg = getattr(event, "message", {}) or {}
    raw = msg.get("raw_eeg", []) if isinstance(msg, dict) else []
    for sample in raw:
        live_buffer.ch1.append(sample.get("ch1", 0.0))
        live_buffer.timestamps.append(sample.get("timestamp", 0.0))
    _dirty = True

async def processing_loop():
    """Process incoming samples without creating or updating any plots."""
    global _dirty, _start_time, _last_state, _last_state_time

    loop = asyncio.get_event_loop()
    _update_dwell_cache()

    _first_data = True
    while live_buffer.is_running:
        if not _dirty:
            await asyncio.sleep(0.01)
            continue

        _dirty = False

        if _first_data:
            _first_data = False
            write_overlay_state("CALIBRATING")
            print("Data flowing — calibration started")

        if len(live_buffer.ch1) < fs * 2:
            await asyncio.sleep(0)
            continue

        data = np.array(live_buffer.ch1, dtype=float)
        filtered = apply_filters(data)
        if len(filtered) < nperseg:
            await asyncio.sleep(0)
            continue

        freqs, psd = await loop.run_in_executor(_executor, _welch_only, filtered)
        if freqs is None:
            await asyncio.sleep(0)
            continue

        if _start_time is None:
            _start_time = live_buffer.timestamps[0]
        current_t = float(live_buffer.timestamps[-1]) - _start_time

        theta_bl = calibration.theta_baseline if calibration.complete else 1e-8
        raw_features = compute_features(freqs, psd, theta_bl)
        smooth_feats = smooth_features(raw_features)

        if not calibration.complete:
            calibration.add_sample(raw_features)
            calibration.add_psd(freqs, psd)
            if current_t >= CALIBRATION_SECONDS:
                calibration.end_time = current_t
                calibration.finalize()
                print(f"Calibration complete. theta_baseline={calibration.theta_baseline:.5f}")
            current_state = "CALIBRATING"
        else:
            current_state = classify(smooth_feats)

        if current_state != _last_state:
            print(f"State: {current_state}")
            _last_state = current_state
            _last_state_time = current_t

        write_overlay_state(current_state, current_t)
        await asyncio.sleep(0)

async def replay_csv(filepath: str, chunk_size: int, speed: float):
    df = pd.read_csv(filepath)
    timestamps = df["timestamp"].values
    values = df["ch1"].values
    t0 = timestamps[0]
    for i in range(0, len(df), chunk_size):
        end = min(i + chunk_size, len(df))
        chunk = [{"timestamp": timestamps[j] - t0, "ch1": values[j]} for j in range(i, end)]
        handle_live_data({"message": {"raw_eeg": chunk}})
        if end < len(df):
            await asyncio.sleep(max((timestamps[end] - timestamps[i]) / speed, 0))
    live_buffer.is_running = False

async def run_live():
    if not _SDK_AVAILABLE:
        raise ImportError(
            "idun_guardian_sdk is not installed. "
            "Run: pip install idun-guardian-sdk"
        )

    client = GuardianClient(api_token=MY_API_TOKEN, address=DEVICE_ADDRESS)
    client.subscribe_live_insights(raw_eeg=True, handler=handle_live_data)
    plot_task = asyncio.create_task(processing_loop())
    try:
        kwargs = {"led_sleep": False, "calc_latency": False}
        if RECORDING_DURATION is not None:
            kwargs["recording_timer"] = RECORDING_DURATION
        await client.start_recording(**kwargs)
    finally:
        live_buffer.is_running = False
        try:
            await plot_task
        except asyncio.CancelledError:
            pass
        try:
            await client.disconnect_device()
        except Exception:
            pass

async def main():
    global _start_time, _dirty

    reset_state()
    reset_filter_state()
    live_buffer.timestamps.clear()
    live_buffer.ch1.clear()
    live_buffer.is_running = True
    _start_time = None
    _dirty = False
    write_overlay_state("CONNECTING")
    print(f"Overlay state file: {OVERLAY_STATE_FILE}")

    try:
        if MODE == "offline":
            plot_task = asyncio.create_task(processing_loop())
            try:
                await replay_csv(CSV_FILE, CHUNK_SIZE, PLAYBACK_SPEED)
            finally:
                live_buffer.is_running = False
                try:
                    await plot_task
                except asyncio.CancelledError:
                    pass
        elif MODE == "live":
            try:
                await run_live()
            finally:
                live_buffer.is_running = False
        else:
            raise ValueError(f"Unknown MODE={MODE!r}. Use 'offline' or 'live'.")
    finally:
        write_overlay_state("CALIBRATING")

if __name__ == "__main__":
    asyncio.run(main())