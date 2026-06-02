"""
lofilia.py — Lofi Girl desktop overlay for the EEG classifier.

Run alongside eeg_backend.py:
    python lofilia.py

Reads state from lofilia_state.txt (written by the classifier every frame).
Right-click to settings or close.
Drag to move.

Required files in the "ui" subfolder:
    edited1.gif        — focused state animation
    edited2.gif        — drifting state animation
    Loading_icon.gif   — calibration animation
    ttsreader_*.mp3    — TTS voice audio files
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import sys
import subprocess
import threading
import socket
import time
import atexit
import json

# ── Config ─────────────────────────────────────────────────────────────────────
OVERLAY_WIDTH = 480
OVERLAY_HEIGHT = 340
POLL_INTERVAL = 1000
FRAME_INTERVAL = 333
BUBBLE_DURATION = 7000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(SCRIPT_DIR, "ui")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "lofilia_config.json")
STATE_FILE = os.path.join(SCRIPT_DIR, "lofilia_state.txt")


LOFI_URL = "https://www.youtube.com/watch?v=5qap5aO4i9A" # for live music from the Lo-Fi Girl YouTube channel
BACKEND_SCRIPT = os.path.join(SCRIPT_DIR, "eeg_backend.py")


GIF_FOCUSED = os.path.join(UI_DIR, "edited1.gif")
GIF_DRIFTING = os.path.join(UI_DIR, "edited2.gif")
GIF_CALIBRATING = os.path.join(UI_DIR, "Loading_icon.gif")

DEFAULT_SETTINGS = {
    "device_address": "E0:53:73:AB:F9:05",
    "use_iaf": True,
    "calibration_seconds": 5.0,
    "playback_speed": 10.0,
}

# TTS audio files matching each DRIFTING message (same order)
DRIFTING_AUDIO = [
    os.path.join(UI_DIR, "ttsreader_i-noticed-.mp3"),
    os.path.join(UI_DIR, "ttsreader_your-conce.mp3"),
    os.path.join(UI_DIR, "ttsreader_looks-like.mp3"),
]


CALIBRATING_AUDIO = [
    os.path.join(UI_DIR, "ttsreader_calibratin.mp3"),
]

MESSAGES = {
    "DRIFTING": [
        "I noticed your mind is wandering, want to take a quick 5 min break?",
        "Your concentration is fading. Try to refocus or take a break.",
        "Looks like you're losing Focus! How about a quick break?",
    ],
    "FOCUSED": [
        "Great focus! Keep it up 🎵",
        "You're in the zone! 📖",
        "Nice work! 🎧",
    ],
    "CALIBRATING": [
        "Calibrating device... Please wait...",
    ],
}
_msg_index = {k: 0 for k in MESSAGES}

BG_COLOR = "#1a1a2e"
BUBBLE_BG = "#ffffff"
BUBBLE_TEXT = "#1a1a2e"
STATUS_COLORS = {
    "FOCUSED":              "#00b894",
    "DRIFTING":             "#e17055",
    "CALIBRATING":          "#a0a0c0",
    "CONNECTING":           "#f0a030",
}

def load_gif(path, size):
    """Load all frames of a GIF, resized to (w, h)."""
    frames = []
    try:
        img = Image.open(path)
        for i in range(getattr(img, "n_frames", 1)):
            img.seek(i)
            frame = img.convert("RGBA").resize(size, Image.LANCZOS)
            frames.append(ImageTk.PhotoImage(frame))
    except Exception as e:
        print(f"Warning: could not load {path}: {e}")
        blank = Image.new("RGBA", size, (30, 30, 50, 255))
        frames.append(ImageTk.PhotoImage(blank))
    return frames

def get_vlc_path():
    """Dynamically resolve VLC path to support 32/64-bit and custom installs."""
    paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

class StartMenu:
    def __init__(self, root):
        self.root = root
        self.root.title("Lofilia Launcher")
        self.root.geometry("420x330")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")
        self.root.attributes("-topmost", True)

        self.settings = self.load_config()

        PAD = 16
        BG = "#1e1e2e"
        FG = "#cdd6f4"
        ACCENT = "#6c5ce7"
        TROUGH = "#313244"

        tk.Label(root, text="Lofilia Launcher", bg=BG, fg=FG, font=("Helvetica", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(14, 6)
        )

        frm = tk.Frame(root, bg=BG)
        frm.pack(fill="both", expand=True, padx=PAD, pady=4)

        def row(label):
            r = tk.Frame(frm, bg=BG)
            r.pack(fill="x", pady=6)
            tk.Label(r, text=label, bg=BG, fg=FG, width=18, anchor="w", font=("Helvetica", 10)).pack(side="left")
            return r

        r1 = row("IDUN MAC address")
        self.mac_var = tk.StringVar(value=self.settings["device_address"])
        tk.Entry(r1, textvariable=self.mac_var, width=24).pack(side="right")

        r2 = row("Use IAF")
        self.use_iaf_var = tk.BooleanVar(value=self.settings["use_iaf"])
        tk.Checkbutton(r2, variable=self.use_iaf_var, bg=BG, fg=FG, activebackground=BG, selectcolor=ACCENT).pack(
            side="right"
        )

        r3 = row("Calibration sec")
        self.calib_var = tk.StringVar(value=str(self.settings["calibration_seconds"]))
        tk.Entry(r3, textvariable=self.calib_var, width=10, justify="center").pack(side="right")

        r4 = row("Playback speed")
        self.speed_var = tk.StringVar(value=str(self.settings["playback_speed"]))
        tk.Entry(r4, textvariable=self.speed_var, width=10, justify="center").pack(side="right")

        btnfrm = tk.Frame(root, bg=BG)
        btnfrm.pack(fill="x", padx=PAD, pady=(10, 12))

        tk.Button(
            btnfrm,
            text="Load recording",
            bg=ACCENT,
            fg="white",
            relief="flat",
            padx=10,
            pady=7,
            command=self.load_recording,
        ).pack(fill="x", pady=4)

        tk.Button(
            btnfrm,
            text="Start live session",
            bg=ACCENT,
            fg="white",
            relief="flat",
            padx=10,
            pady=7,
            command=self.start_live,
        ).pack(fill="x", pady=4)

        tk.Button(
            btnfrm,
            text="Quit",
            bg="#3b3b4f",
            fg=FG,
            relief="flat",
            padx=10,
            pady=7,
            command=self.root.destroy,
        ).pack(fill="x", pady=(8, 0))

        self._backend_proc = None

    def load_config(self):
        cfg = DEFAULT_SETTINGS.copy()
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cfg.update({k: data.get(k, cfg[k]) for k in cfg})
        except Exception:
            pass
        return cfg

    def save_config(self):
        self.settings = {
            "device_address": self.mac_var.get().strip(),
            "use_iaf": bool(self.use_iaf_var.get()),
            "calibration_seconds": float(self.calib_var.get()),
            "playback_speed": float(self.speed_var.get()),
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2)

    def validate_settings(self, for_offline=False):
        mac = self.mac_var.get().strip()
        if not mac:
            messagebox.showerror("Invalid input", "Please enter the IDUN MAC address.")
            return None

        try:
            calibration_seconds = float(self.calib_var.get())
            playback_speed = float(self.speed_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Calibration seconds and playback speed must be numeric.")
            return None

        if calibration_seconds <= 0:
            messagebox.showerror("Invalid input", "Calibration seconds must be greater than 0.")
            return None
        if for_offline and playback_speed <= 0:
            messagebox.showerror("Invalid input", "Playback speed must be greater than 0.")
            return None

        return {
            "device_address": mac,
            "use_iaf": self.use_iaf_var.get(),
            "calibration_seconds": calibration_seconds,
            "playback_speed": playback_speed,
        }

    def start_backend(self, args):
        try:
            self.save_config()
        except Exception as e:
            messagebox.showerror("Config error", f"Could not save settings: {e}")
            return

        try:
            self._backend_proc = subprocess.Popen([sys.executable, BACKEND_SCRIPT] + args, cwd=SCRIPT_DIR)
        except Exception as e:
            messagebox.showerror("Launch error", f"Could not start backend: {e}")
            return

        self.root.after(250, self.launch_overlay)

    def load_recording(self):
        settings = self.validate_settings(for_offline=True)
        if settings is None:
            return

        csv_file = filedialog.askopenfilename(
            title="Select EEG recording CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_file:
            return

        args = [
            "--mode", "offline",
            "--csv-file", csv_file,
            "--use-iaf", str(settings["use_iaf"]),
            "--calibration-seconds", str(settings["calibration_seconds"]),
            "--playback-speed", str(settings["playback_speed"]),
        ]
        self.start_backend(args)

    def start_live(self):
        settings = self.validate_settings(for_offline=False)
        if settings is None:
            return

        args = [
            "--mode", "live",
            "--device-address", settings["device_address"],
            "--use-iaf", str(settings["use_iaf"]),
            "--calibration-seconds", str(settings["calibration_seconds"]),
        ]
        self.start_backend(args)

    def launch_overlay(self):
        backend_proc = self._backend_proc
        try:
            self.root.destroy()
        except Exception:
            pass
        try:
            overlay_root = tk.Tk()
            app = LofiliApp(overlay_root)
            app._backend_proc = backend_proc  # hand off so overlay can stop it
            overlay_root.mainloop()
        except Exception as e:
            messagebox.showerror("Overlay error", f"Could not launch overlay: {e}")

class LofiliApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Lofilia")
        self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+60+60")
        self.root.configure(bg=BG_COLOR)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)
        self.root.overrideredirect(True)
        self.root.protocol("WM_DELETE_WINDOW", self._return_to_menu)

        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_motion)
        self.root.bind("<ButtonPress-3>", self._show_menu)
        self._drag_x = self._drag_y = 0

        self.canvas = tk.Canvas(
            root, width=OVERLAY_WIDTH, height=OVERLAY_HEIGHT,
            bg=BG_COLOR, highlightthickness=0
        )
        self.canvas.pack()

        gif_size = (OVERLAY_WIDTH, OVERLAY_HEIGHT - 40)
        print("Loading GIFs...")
        self.frames = {
            "FOCUSED": load_gif(GIF_FOCUSED, gif_size),
            "DRIFTING": load_gif(GIF_DRIFTING, gif_size),
            "CALIBRATING": load_gif(GIF_CALIBRATING, gif_size),
            "CONNECTING":   load_gif(GIF_CALIBRATING, gif_size),
        }
        print(f"  FOCUSED:  {len(self.frames['FOCUSED'])} frames")
        print(f"  DRIFTING: {len(self.frames['DRIFTING'])} frames")

        self.state = "CALIBRATING"
        self.prev_state = None
        self._frame_idx = 0
        self._bubble_text = ""
        self._bubble_job = None
        self._drift_repeat_job = None  # repeating reminder while DRIFTING
        self._frame_interval = FRAME_INTERVAL
        self._opacity = 0.97
        self._music_proc = None
        self._music_on = True
        self._backend_proc = None  # set by StartMenu.launch_overlay
        self._music_paused = False
        self._vlc_rc_port = 9999
        self._music_volume = 80
        self._music_volume = 100
        self._vlc_lock = threading.Lock()
        self._calib_start_time = 0
        self._last_state_update = 0.0
        self._calib_progress = 0.0
        self._calib_seconds = 60.0
        self._engagement = None
        self._relaxation = None
        self._paf = None

        atexit.register(self._cleanup)

        self._poll()
        self._animate()

    def _cleanup(self):
        self._stop_music()
        self._stop_backend()

    def _stop_backend(self):
        proc = getattr(self, "_backend_proc", None)
        if not proc:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=2)
            print("Backend stopped")
        except Exception as e:
            print(f"Backend stop error: {e}")
        self._backend_proc = None

    def _drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _drag_motion(self, e):
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Settings...", command=self._show_settings)
        menu.add_separator()
        menu.add_command(label="Return to menu", command=self._return_to_menu)
        menu.tk_popup(e.x_root, e.y_root)

    def _show_settings(self):
        if hasattr(self, "_settings_win") and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return

        win = tk.Toplevel(self.root)
        win.title("Lofilia Settings")
        win.geometry("360x470")
        win.configure(bg="#1e1e2e")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self._settings_win = win

        PAD = 16
        BG = "#1e1e2e"
        FG = "#cdd6f4"
        ACCENT = "#6c5ce7"
        TROUGH = "#313244"

        p = {
            "fps": round(1000 / self._frame_interval, 1),
            "opacity": int(self._opacity * 100),
            "scale": getattr(self, "_overlay_scale", 100),
            "music_on": self._music_on,
            "music_vol": self._music_volume,
            "tts_vol": self._music_volume,
            "bubble_dur": BUBBLE_DURATION // 1000,
        }

        def section(text):
            tk.Frame(win, bg=ACCENT, height=1).pack(fill="x", padx=PAD, pady=(14, 0))
            tk.Label(win, text=text, bg=BG, fg=ACCENT, font=("Helvetica", 10, "bold")).pack(
                anchor="w", padx=PAD, pady=(4, 0)
            )

        def slider_row(label, key, from_, to, resolution, fmt=None):
            if fmt is None:
                fmt = lambda v: f"{float(v):.0f}"
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=PAD, pady=4)
            tk.Label(row, text=label, bg=BG, fg=FG, width=20, anchor="w", font=("Helvetica", 9)).pack(side="left")
            val_lbl = tk.Label(row, text=fmt(p[key]), bg=BG, fg=ACCENT, width=6, font=("Helvetica", 9, "bold"))
            val_lbl.pack(side="right")

            def on_change(v, lbl=val_lbl, k=key, f=fmt):
                lbl.config(text=f(float(v)))
                p[k] = float(v)

            s = tk.Scale(
                row,
                from_=from_,
                to=to,
                resolution=resolution,
                orient="horizontal",
                bg=BG,
                fg="white",
                troughcolor=TROUGH,
                activebackground="white",
                highlightthickness=0,
                bd=0,
                sliderrelief="flat",
                command=on_change,
                showvalue=False,
                length=160,
            )
            s.set(p[key])
            s.pack(side="right", padx=(0, 6))

        section("Animation")
        slider_row("Framerate (fps)", "fps", 0.5, 12, 0.5, fmt=lambda v: f"{float(v):.1f}")
        slider_row("Opacity (%)", "opacity", 10, 100, 5)
        slider_row("Overlay Size (%)", "scale", 50, 200, 10)

        section("Audio")
        music_var = tk.BooleanVar(value=p["music_on"])
        music_row = tk.Frame(win, bg=BG)
        music_row.pack(fill="x", padx=PAD, pady=4)
        tk.Label(music_row, text="Audio On/Off", bg=BG, fg=FG, width=20, anchor="w", font=("Helvetica", 9)).pack(
            side="left"
        )

        def on_music_toggle():
            p["music_on"] = music_var.get()

        tk.Checkbutton(
            music_row,
            variable=music_var,
            bg=BG,
            fg=FG,
            activebackground=BG,
            selectcolor=ACCENT,
            command=on_music_toggle,
        ).pack(side="right")

        slider_row("Volume (%)", "music_vol", 0, 150, 5)
        slider_row("Voice Volume (%)", "tts_vol", 0, 150, 5)
        slider_row("Bubble Duration (s)", "bubble_dur", 2, 20, 1)

        def save():
            global BUBBLE_DURATION
            self._frame_interval = int(1000 / max(0.5, p["fps"]))
            self._opacity = p["opacity"] / 100
            self.root.attributes("-alpha", self._opacity)

            scale = int(p["scale"])
            self._overlay_scale = scale
            w = int(OVERLAY_WIDTH * scale / 100)
            h = int(OVERLAY_HEIGHT * scale / 100)
            gif_size = (w, h - 40)
            for state, path in [("FOCUSED", GIF_FOCUSED), ("DRIFTING", GIF_DRIFTING),
                                 ("CALIBRATING", GIF_CALIBRATING),
                                 ("CONNECTING", GIF_CALIBRATING)]:
                self.frames[state] = load_gif(path, gif_size)
            self.canvas.config(width=w, height=h)
            self.root.geometry(f"{w}x{h}")

            if p["music_on"] != self._music_on:
                self._toggle_music()
            self._music_volume = int(p["music_vol"])
            self._music_volume = int(p["tts_vol"])
            if self._music_on:
                self._vlc_command(f"volume {self._music_volume}")
            BUBBLE_DURATION = int(p["bubble_dur"]) * 1000

            win.destroy()

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=16)
        tk.Button(
            btn_row, text=" Save ", bg=ACCENT, fg="white", font=("Helvetica", 10, "bold"),
            relief="flat", padx=10, pady=5, cursor="hand2", command=save
        ).pack(side="left", padx=6)
        tk.Button(
            btn_row, text=" Cancel ", bg=TROUGH, fg=FG, font=("Helvetica", 10),
            relief="flat", padx=10, pady=5, cursor="hand2", command=win.destroy
        ).pack(side="left", padx=6)

    def _toggle_music(self):
        if self._music_on:
            self._stop_music()
        else:
            self._start_music()

    def _set_music_volume(self, vol: int):
        self._music_volume = vol
        if self._music_on and not self._music_paused:
            self._vlc_command(f"volume {self._music_volume}")

    def _start_music(self):
        """Extract stream URL via yt-dlp, then play with VLC in background."""
        self._music_on = True

        def _run():
            try:
                import sys as _sys
                stream_url = None
                for fmt in ["93", "94", "bestaudio", "best"]:
                    result = subprocess.run(
                        [_sys.executable, "-m", "yt_dlp", "-g", "-f", fmt, LOFI_URL],
                        capture_output=True, text=True, timeout=30
                    )
                    url = result.stdout.strip().split("\n")[0]
                    if url.startswith("http"):
                        stream_url = url
                        print(f"Stream URL found with format: {fmt}")
                        break

                if not stream_url:
                    print(f"Could not get stream URL. yt-dlp stderr: {result.stderr[:300]}")
                    self._music_on = False
                    return

                vlc_path = get_vlc_path()
                if not vlc_path:
                    print("Error: VLC path not found. Please install VLC.")
                    self._music_on = False
                    return

                self._music_proc = subprocess.Popen(
                    [
                        vlc_path, "--intf", "rc",
                        f"--rc-host=localhost:{self._vlc_rc_port}",
                        "--no-video",
                        f"--volume={self._music_volume}",
                        stream_url,
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self._music_paused = False
                print(f"Music playing via VLC (RC port {self._vlc_rc_port})")

                def set_initial_volume():
                    time.sleep(2)
                    self._vlc_command(f"volume {self._music_volume}")

                threading.Thread(target=set_initial_volume, daemon=True).start()

            except FileNotFoundError as ex:
                print(f"Missing tool: {ex}. Install yt-dlp and VLC.")
                self._music_on = False
            except Exception as ex:
                print(f"Music error: {ex}")
                self._music_on = False

        threading.Thread(target=_run, daemon=True).start()

    def _vlc_command(self, cmd: str):
        """Send command to VLC RC interface. Reconnects each call — robust to dropped connections."""
        with self._vlc_lock:
            try:
                with socket.create_connection(("localhost", self._vlc_rc_port), timeout=2) as s:
                    s.sendall((cmd + "\n").encode())
                    s.recv(1024)  # drain response so socket closes cleanly
            except Exception:
                pass

    def _pause_music(self):
        if self._music_on and not self._music_paused:
            self._music_paused = True
            # Retry a few times with delay to ensure VLC receives it
            for _ in range(3):
                self._vlc_command("volume 0")
                time.sleep(0.3)
                if not self._music_paused:  # state changed back, stop retrying
                    break

    def _resume_music(self):
        if self._music_on and self._music_paused:
            self._music_paused = False
            # Retry to ensure volume is properly restored
            for _ in range(3):
                self._vlc_command(f"volume {self._music_volume}")
                time.sleep(0.3)
                if self._music_paused:  # drifted again, stop retrying
                    break

    def _stop_music(self):
        self._music_on = False
        self._music_paused = False
        if self._music_proc:
            self._music_proc.terminate()
            self._music_proc = None
        print("Music stopped")

    def _return_to_menu(self):
        """Stop the session and return to the main launcher menu."""
        try:
            self._stop_music()
        except Exception:
            pass
        try:
            self._stop_backend()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        launch_menu()

    def _force_state(self, state):
        self.state = state

    def _poll(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                state = raw
                if raw.startswith("{"):
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        state = data.get("state", "CALIBRATING")
                        self._calib_progress = float(data.get("calibration_progress", 0.0))
                        self._calib_seconds  = float(data.get("calibration_seconds", 60.0))
                        e = data.get("engagement")
                        r = data.get("relaxation")
                        self._engagement = float(e) if e is not None else None
                        self._relaxation = float(r) if r is not None else None
                        p = data.get("paf")
                        self._paf = float(p) if p is not None else None
                if state in self.frames:
                    self.state = state
                    self._last_state_update = time.time()
        except Exception:
            pass
        self.root.after(POLL_INTERVAL, self._poll)

    def _animate(self):
        if self.state != self.prev_state:
            self._frame_idx = 0

            # Calibration just completed — announce it before switching to new state bubble
            if self.prev_state == "CALIBRATING" and self.state != "CALIBRATING":
                calib_msg = "Calibration complete! Let's get to work 🎉"
                self._bubble_text = calib_msg
                calib_audio = os.path.join(UI_DIR, "ttsreader_calibratio.mp3")
                self._play_tts(calib_audio)
                if self._bubble_job:
                    self.root.after_cancel(self._bubble_job)
                self._bubble_job = self.root.after(4000, self._show_bubble)
            else:
                self._show_bubble()

            if self.state == "DRIFTING":
                threading.Thread(target=self._pause_music, daemon=True).start()
                self._schedule_drift_repeat()
            elif self.prev_state == "DRIFTING":
                threading.Thread(target=self._resume_music, daemon=True).start()
                self._cancel_drift_repeat()

            if self.state == "CALIBRATING":
                self._calib_start_time = time.time()

            self.prev_state = self.state

        frames = self.frames.get(self.state, self.frames["FOCUSED"])
        frame = frames[self._frame_idx % len(frames)]
        self._frame_idx += 1

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=frame)

        cw = self.canvas.winfo_width() or OVERLAY_WIDTH
        ch = self.canvas.winfo_height() or OVERLAY_HEIGHT
        bar_y = ch - 40
        self.canvas.create_rectangle(0, bar_y, cw, ch, fill=BG_COLOR, outline="")

        dot_color = STATUS_COLORS.get(self.state, "#aaa")
        self.canvas.create_oval(12, bar_y + 12, 24, bar_y + 24, fill=dot_color, outline="")

        if self.state == "CONNECTING":
            label = "Connecting to device..."
        elif self.state == "CALIBRATING":
            remaining = max(0, int(self._calib_seconds * (1.0 - self._calib_progress)))
            label = f"Calibrating... {remaining}s"
        else:
            if self._engagement is not None and self._relaxation is not None:
                diff = self._engagement - self._relaxation
                label = f"{self.state}  ({diff:+.2f})"
            else:
                label = self.state

        self.canvas.create_text(
            34, bar_y + 18, text=label, anchor="w", fill=dot_color, font=("Courier", 10, "bold")
        )

        # PAF display — small text above bar, bottom left
        if self._paf is not None:
            self.canvas.create_text(
                8, bar_y - 6, text=f"PAF {self._paf:.1f} Hz",
                anchor="w", fill="#000000", font=("Courier", 8)
            )

        self.canvas.create_text(
            cw - 14, bar_y + 18, text="✕", anchor="e", fill="#666",
            font=("Courier", 12, "bold"), tags="close_btn"
        )
        self.canvas.tag_bind("close_btn", "<Button-1>", lambda e: self._return_to_menu())

        if self._bubble_text:
            self._draw_bubble(self._bubble_text)

        self.root.after(self._frame_interval, self._animate)

    def _draw_bubble(self, text: str):
        c = self.canvas
        bx, by = 8, 8
        bw, bh = 220, 60
        r = 10

        c.create_rectangle(bx + r, by, bx + bw - r, by + bh, fill=BUBBLE_BG, outline="")
        c.create_rectangle(bx, by + r, bx + bw, by + bh - r, fill=BUBBLE_BG, outline="")
        c.create_oval(bx, by, bx + 2 * r, by + 2 * r, fill=BUBBLE_BG, outline="")
        c.create_oval(bx + bw - 2 * r, by, bx + bw, by + 2 * r, fill=BUBBLE_BG, outline="")
        c.create_oval(bx, by + bh - 2 * r, bx + 2 * r, by + bh, fill=BUBBLE_BG, outline="")
        c.create_oval(bx + bw - 2 * r, by + bh - 2 * r, bx + bw, by + bh, fill=BUBBLE_BG, outline="")

        c.create_polygon(
            bx + bw // 2 - 8, by + bh,
            bx + bw // 2 + 8, by + bh,
            bx + bw // 2, by + bh + 12,
            fill=BUBBLE_BG, outline=""
        )

        c.create_text(
            bx + bw // 2, by + bh // 2, text=text, fill=BUBBLE_TEXT,
            font=("Helvetica", 10, "bold"), width=bw - 16, justify="center"
        )

    def _play_tts(self, audio_file):
        """Threaded, fail-safe TTS playback handler."""
        if not os.path.exists(audio_file):
            print(f"TTS: file not found: {audio_file}")
            return

        def _play():
            try:
                vlc_path = get_vlc_path()
                if not vlc_path:
                    print("TTS Error: VLC path not found.")
                    return
                print(f"TTS: playing {os.path.basename(audio_file)} at vol={self._music_volume}")
                result = subprocess.run(
                    [
                        vlc_path, "--intf", "dummy", "--no-video",
                        f"--volume={self._music_volume}",
                        "--play-and-exit", audio_file
                    ],
                    capture_output=True, timeout=30
                )
                if result.returncode != 0:
                    print(f"TTS VLC error: {result.stderr[:200].decode(errors='ignore')}")
            except Exception as e:
                print(f"TTS Error: {e}")

        threading.Thread(target=_play, daemon=True).start()

    def _schedule_drift_repeat(self):
        """Re-trigger the drifting message+audio every 6s while state stays DRIFTING."""
        self._cancel_drift_repeat()
        self._drift_repeat_job = self.root.after(6000, self._drift_repeat)

    def _cancel_drift_repeat(self):
        if self._drift_repeat_job:
            self.root.after_cancel(self._drift_repeat_job)
            self._drift_repeat_job = None

    def _drift_repeat(self):
        """Called every 6s while still DRIFTING — show next message and reschedule."""
        if self.state == "DRIFTING":
            self._show_bubble()
            self._schedule_drift_repeat()

    def _show_bubble(self):
        msgs = MESSAGES.get(self.state, [])
        if not msgs:
            return
        idx = _msg_index[self.state] % len(msgs)
        self._bubble_text = msgs[idx]
        _msg_index[self.state] = idx + 1

        if self.state == "DRIFTING" and idx < len(DRIFTING_AUDIO):
            self._play_tts(DRIFTING_AUDIO[idx])

        if self.state == "CALIBRATING" and idx < len(CALIBRATING_AUDIO):
            self._play_tts(CALIBRATING_AUDIO[idx])

        if self._bubble_job:
            self.root.after_cancel(self._bubble_job)
        self._bubble_job = self.root.after(BUBBLE_DURATION, self._hide_bubble)

    def _hide_bubble(self):
        self._bubble_text = ""
        self._bubble_job = None
        self._drift_repeat_job = None  # repeating reminder while DRIFTING

def launch_menu():
    root = tk.Tk()
    StartMenu(root)
    root.mainloop()

def main():
    launch_menu()

if __name__ == "__main__":
    main()