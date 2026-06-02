"""
lofilia.py — Lofi Girl desktop overlay for the EEG classifier.

Run alongside eeg_classifier.ipynb:
    python lofilia.py

Reads state from lofilia_state.txt (written by the classifier every frame).
Right-click to demo states or close.
Drag to move.

Required files in the same folder:
    edited1.gif       — focused state animation
    lofi_drifting.gif — drifting state animation
"""

import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os
import sys
import subprocess
import threading
import socket
import time

# ── Config ─────────────────────────────────────────────────────────────────────
OVERLAY_WIDTH   = 480
OVERLAY_HEIGHT  = 340
POLL_INTERVAL   = 500    # ms between state file reads
FRAME_INTERVAL  = 333    # ms between gif frames (~3fps default)
BUBBLE_DURATION = 7000   # ms before speech bubble hides

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
LOFI_URL    = "https://www.youtube.com/watch?v=EWrX250Zhko"
STATE_FILE = os.path.join(SCRIPT_DIR, "lofilia_state.txt")
GIF_FOCUSED   = os.path.join(SCRIPT_DIR, "edited1.gif")
GIF_DRIFTING  = os.path.join(SCRIPT_DIR, "edited2.gif")

# TTS audio files matching each DRIFTING message (same order)
DRIFTING_AUDIO = [
    os.path.join(SCRIPT_DIR, "ttsreader_i-noticed-.mp3"),
    os.path.join(SCRIPT_DIR, "ttsreader_your-conce.mp3"),
    os.path.join(SCRIPT_DIR, "ttsreader_looks-like.mp3"),
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
        "Calibrating... sit still 🎧",
        "Measuring your baseline...",
    ],
}
_msg_index = {k: 0 for k in MESSAGES}

BG_COLOR      = "#1a1a2e"
BUBBLE_BG     = "#ffffff"
BUBBLE_TEXT   = "#1a1a2e"
STATUS_COLORS = {
    "FOCUSED":     "#00b894",
    "DRIFTING":    "#e17055",
    "CALIBRATING": "#a0a0c0",
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
        # Fallback: blank frame
        blank = Image.new("RGBA", size, (30, 30, 50, 255))
        frames.append(ImageTk.PhotoImage(blank))
    return frames


class LofiliApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Lofilia")
        self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+60+60")
        self.root.configure(bg=BG_COLOR)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)
        self.root.overrideredirect(True)

        self.root.bind("<ButtonPress-1>",  self._drag_start)
        self.root.bind("<B1-Motion>",      self._drag_motion)
        self.root.bind("<ButtonPress-3>",  self._show_menu)
        self._drag_x = self._drag_y = 0

        # Canvas
        self.canvas = tk.Canvas(
            root, width=OVERLAY_WIDTH, height=OVERLAY_HEIGHT,
            bg=BG_COLOR, highlightthickness=0
        )
        self.canvas.pack()

        # Load GIF frames
        gif_size = (OVERLAY_WIDTH, OVERLAY_HEIGHT - 40)
        print("Loading GIFs...")
        self.frames = {
            "FOCUSED":     load_gif(GIF_FOCUSED,  gif_size),
            "DRIFTING":    load_gif(GIF_DRIFTING, gif_size),
            "CALIBRATING": load_gif(GIF_FOCUSED,  gif_size),  # reuse focused during calib
        }
        print(f"  FOCUSED:  {len(self.frames['FOCUSED'])} frames")
        print(f"  DRIFTING: {len(self.frames['DRIFTING'])} frames")

        self.state            = "CALIBRATING"
        self.prev_state       = None
        self._frame_idx       = 0
        self._bubble_text     = ""
        self._bubble_job      = None
        self._frame_interval  = FRAME_INTERVAL
        self._opacity         = 0.97
        self._music_proc      = None   # subprocess handle for VLC
        self._music_on        = False
        self._music_paused    = False
        self._vlc_rc_port     = 9999   # VLC remote control port
        self._music_volume    = 80    # 0-200 (VLC scale) — lofi stream
        self._tts_volume      = 100   # 0-200 (VLC scale) — TTS voice

        self._poll()
        self._animate()

    # ── Drag ───────────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _drag_motion(self, e):
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Demo: FOCUSED",     command=lambda: self._force_state("FOCUSED"))
        menu.add_command(label="Demo: DRIFTING",    command=lambda: self._force_state("DRIFTING"))
        menu.add_command(label="Demo: CALIBRATING", command=lambda: self._force_state("CALIBRATING"))
        menu.add_separator()
        menu.add_command(label="\u2699\ufe0f  Settings...", command=self._show_settings)
        menu.add_separator()
        menu.add_command(label="Close", command=self._quit)
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

        PAD    = 16
        BG     = "#1e1e2e"
        FG     = "#cdd6f4"
        ACCENT = "#6c5ce7"
        TROUGH = "#313244"

        # ── Pending values (only applied on Save) ─────────────────────────────
        p = {
            "fps":          round(1000 / self._frame_interval, 1),
            "opacity":      int(self._opacity * 100),
            "scale":        getattr(self, "_overlay_scale", 100),
            "music_on":     self._music_on,
            "music_vol":    self._music_volume,
            "tts_vol":      self._tts_volume,
            "bubble_dur":   BUBBLE_DURATION // 1000,
        }

        def section(text):
            tk.Frame(win, bg=ACCENT, height=1).pack(fill="x", padx=PAD, pady=(14, 0))
            tk.Label(win, text=text, bg=BG, fg=ACCENT,
                     font=("Helvetica", 10, "bold")).pack(anchor="w", padx=PAD, pady=(4, 0))

        def slider_row(label, key, from_, to, resolution, fmt=None):
            if fmt is None:
                fmt = lambda v: f"{float(v):.0f}"
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=PAD, pady=4)
            tk.Label(row, text=label, bg=BG, fg=FG, width=20, anchor="w",
                     font=("Helvetica", 9)).pack(side="left")
            val_lbl = tk.Label(row, text=fmt(p[key]), bg=BG, fg=ACCENT,
                               width=6, font=("Helvetica", 9, "bold"))
            val_lbl.pack(side="right")
            def on_change(v, lbl=val_lbl, k=key, f=fmt):
                lbl.config(text=f(float(v)))
                p[k] = float(v)
            s = tk.Scale(row, from_=from_, to=to, resolution=resolution,
                         orient="horizontal", bg=BG, fg="white",
                         troughcolor=TROUGH, activebackground="white",
                         highlightthickness=0, bd=0, sliderrelief="flat",
                         command=on_change, showvalue=False, length=160)
            s.set(p[key])
            s.pack(side="right", padx=(0, 6))

        # Animation
        section("Animation")
        slider_row("Framerate (fps)", "fps", 0.5, 12, 0.5, fmt=lambda v: f"{float(v):.1f}")
        slider_row("Opacity (%)",     "opacity", 10, 100, 5)
        slider_row("Overlay Size (%)", "scale", 50, 200, 10)

        # Audio
        section("Audio")
        music_var = tk.BooleanVar(value=p["music_on"])
        music_row = tk.Frame(win, bg=BG)
        music_row.pack(fill="x", padx=PAD, pady=4)
        tk.Label(music_row, text="Lofi Stream", bg=BG, fg=FG, width=20, anchor="w",
                 font=("Helvetica", 9)).pack(side="left")
        def on_music_toggle():
            p["music_on"] = music_var.get()
        tk.Checkbutton(music_row, variable=music_var, bg=BG, fg=FG,
                       activebackground=BG, selectcolor=ACCENT,
                       command=on_music_toggle).pack(side="right")

        slider_row("Music Volume (%)", "music_vol", 0, 150, 5)
        slider_row("Voice Volume (%)", "tts_vol",   0, 150, 5)
        slider_row("Bubble Duration (s)", "bubble_dur", 2, 20, 1)

        # ── Save / Cancel ─────────────────────────────────────────────────────
        def save():
            global BUBBLE_DURATION
            # Animation
            self._frame_interval = int(1000 / max(0.5, p["fps"]))
            self._opacity = p["opacity"] / 100
            self.root.attributes("-alpha", self._opacity)

            # Size
            scale = int(p["scale"])
            self._overlay_scale = scale
            w = int(OVERLAY_WIDTH  * scale / 100)
            h = int(OVERLAY_HEIGHT * scale / 100)
            gif_size = (w, h - 40)
            for state, path in [("FOCUSED", GIF_FOCUSED), ("DRIFTING", GIF_DRIFTING),
                                 ("CALIBRATING", GIF_FOCUSED)]:
                self.frames[state] = load_gif(path, gif_size)
            self.canvas.config(width=w, height=h)
            self.root.geometry(f"{w}x{h}")

            # Audio
            if p["music_on"] != self._music_on:
                self._toggle_music()
            self._music_volume = int(p["music_vol"])
            self._tts_volume   = int(p["tts_vol"])
            if self._music_on:
                self._vlc_command(f"volume {self._music_volume}")
            BUBBLE_DURATION = int(p["bubble_dur"]) * 1000

            win.destroy()

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=16)
        tk.Button(btn_row, text="  Save  ", bg=ACCENT, fg="white",
                  font=("Helvetica", 10, "bold"), relief="flat",
                  padx=10, pady=5, cursor="hand2",
                  command=save).pack(side="left", padx=6)
        tk.Button(btn_row, text=" Cancel ", bg=TROUGH, fg=FG,
                  font=("Helvetica", 10), relief="flat",
                  padx=10, pady=5, cursor="hand2",
                  command=win.destroy).pack(side="left", padx=6)

    def _set_opacity(self, value: float):
        self._opacity = value
        self.root.attributes("-alpha", value)

    # ── Music ──────────────────────────────────────────────────────────────────
    def _toggle_music(self):
        if self._music_on:
            self._stop_music()
        else:
            self._start_music()

    def _set_music_volume(self, vol: int):
        self._music_volume = vol
        if self._music_on:
            self._stop_music()
            self._start_music()

    def _set_tts_volume(self, vol: int):
        self._tts_volume = vol

    def _custom_volume(self, target: str):
        current = self._music_volume if target == "music" else self._tts_volume
        title   = "Music Volume" if target == "music" else "Voice Volume"
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("200x90")
        win.attributes("-topmost", True)
        tk.Label(win, text=f"{title} % (0-200):").pack(pady=6)
        entry = tk.Entry(win, width=8, justify="center")
        entry.insert(0, str(current))
        entry.pack()
        def apply():
            try:
                val = max(0, min(200, int(entry.get())))
                if target == "music":
                    self._set_music_volume(val)
                else:
                    self._set_tts_volume(val)
            except ValueError:
                pass
            win.destroy()
        tk.Button(win, text="Apply", command=apply).pack(pady=6)

    def _start_music(self):
        """Extract stream URL via yt-dlp, then play with VLC in background."""
        self._music_on = True
        def _run():
            try:
                # Get best audio stream URL — try multiple format selectors
                # Live streams may need 93/94/best rather than bestaudio
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
                # Play with VLC headless + RC interface for pause/resume control
                vlc_path = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
                self._music_proc = subprocess.Popen(
                    [vlc_path, "--intf", "rc",
                     f"--rc-host=localhost:{self._vlc_rc_port}",
                     "--no-video",
                     f"--volume={self._music_volume}",
                     stream_url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self._music_paused = False
                print(f"Music playing via VLC (RC port {self._vlc_rc_port})")
            except FileNotFoundError as ex:
                print(f"Missing tool: {ex}. Install yt-dlp and VLC.")
                self._music_on = False
            except Exception as ex:
                print(f"Music error: {ex}")
                self._music_on = False
        threading.Thread(target=_run, daemon=True).start()

    def _vlc_command(self, cmd: str):
        """Send a command to VLC via RC interface."""
        try:
            with socket.create_connection(("localhost", self._vlc_rc_port), timeout=1) as s:
                s.sendall((cmd + "\n").encode())
        except Exception:
            pass

    def _pause_music(self):
        """Mute VLC when drifting — keeps the stream alive."""
        if self._music_on and not self._music_paused:
            self._vlc_command("volume 0")
            self._music_paused = True

    def _resume_music(self):
        """Restore volume when focused again."""
        if self._music_on and self._music_paused:
            self._vlc_command(f"volume {self._music_volume}")
            self._music_paused = False

    def _stop_music(self):
        self._music_on = False
        self._music_paused = False
        if self._music_proc:
            self._music_proc.terminate()
            self._music_proc = None
        print("Music stopped")

    def _quit(self):
        self._stop_music()
        self.root.destroy()

    def _force_state(self, state):
        self.state = state

    # ── State polling ──────────────────────────────────────────────────────────
    def _poll(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    s = f.read().strip()
                if s in self.frames:
                    self.state = s
        except Exception:
            pass
        self.root.after(POLL_INTERVAL, self._poll)

    # ── Animation ──────────────────────────────────────────────────────────────
    def _animate(self):
        # Reset frame index on state change
        if self.state != self.prev_state:
            self._frame_idx = 0
            self._show_bubble()
            # Pause music when drifting, resume when focused
            if self.state == "DRIFTING":
                threading.Thread(target=self._pause_music, daemon=True).start()
            elif self.prev_state == "DRIFTING":
                threading.Thread(target=self._resume_music, daemon=True).start()
            self.prev_state = self.state

        frames = self.frames.get(self.state, self.frames["FOCUSED"])
        frame  = frames[self._frame_idx % len(frames)]
        self._frame_idx += 1

        self.canvas.delete("all")

        # GIF image
        self.canvas.create_image(0, 0, anchor="nw", image=frame)

        # Bottom bar — use actual canvas dimensions so it works after resize
        cw = self.canvas.winfo_width()  or OVERLAY_WIDTH
        ch = self.canvas.winfo_height() or OVERLAY_HEIGHT
        bar_y = ch - 40
        self.canvas.create_rectangle(0, bar_y, cw, ch, fill=BG_COLOR, outline="")

        # Status dot + label
        dot_color = STATUS_COLORS.get(self.state, "#aaa")
        self.canvas.create_oval(12, bar_y + 12, 24, bar_y + 24,
                                fill=dot_color, outline="")
        label = self.state if self.state != "CALIBRATING" else "Calibrating..."
        self.canvas.create_text(34, bar_y + 18, text=label,
                                anchor="w", fill=dot_color,
                                font=("Courier", 10, "bold"))

        # Close button
        self.canvas.create_text(cw - 14, bar_y + 18,
                                text="✕", anchor="e", fill="#666",
                                font=("Courier", 12, "bold"),
                                tags="close_btn")
        self.canvas.tag_bind("close_btn", "<Button-1>", lambda e: self._quit())

        # Speech bubble
        if self._bubble_text:
            self._draw_bubble(self._bubble_text)

        self.root.after(self._frame_interval, self._animate)

    def _draw_bubble(self, text: str):
        c = self.canvas
        bx, by = 8, 8
        bw, bh = 220, 60
        r = 10

        # Rounded rectangle
        c.create_rectangle(bx+r, by,    bx+bw-r, by+bh, fill=BUBBLE_BG, outline="")
        c.create_rectangle(bx,   by+r,  bx+bw,   by+bh-r, fill=BUBBLE_BG, outline="")
        c.create_oval(bx,      by,      bx+2*r,  by+2*r,  fill=BUBBLE_BG, outline="")
        c.create_oval(bx+bw-2*r, by,    bx+bw,   by+2*r,  fill=BUBBLE_BG, outline="")
        c.create_oval(bx,      by+bh-2*r, bx+2*r, by+bh,  fill=BUBBLE_BG, outline="")
        c.create_oval(bx+bw-2*r, by+bh-2*r, bx+bw, by+bh, fill=BUBBLE_BG, outline="")

        # Tail
        c.create_polygon(bx+bw//2-8, by+bh,
                         bx+bw//2+8, by+bh,
                         bx+bw//2,   by+bh+12,
                         fill=BUBBLE_BG, outline="")

        # Text
        c.create_text(bx + bw//2, by + bh//2,
                      text=text, fill=BUBBLE_TEXT,
                      font=("Helvetica", 10, "bold"),
                      width=bw - 16, justify="center")

    def _show_bubble(self):
        msgs = MESSAGES.get(self.state, [])
        if not msgs:
            return
        idx = _msg_index[self.state] % len(msgs)
        self._bubble_text = msgs[idx]
        _msg_index[self.state] = idx + 1

        # Play corresponding TTS audio for DRIFTING messages
        if self.state == "DRIFTING" and idx < len(DRIFTING_AUDIO):
            audio_file = DRIFTING_AUDIO[idx]
            if os.path.exists(audio_file):
                def _play():
                    vlc_path = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
                    subprocess.Popen(
                        [vlc_path, "--intf", "dummy", "--no-video",
                         f"--volume={self._tts_volume}",
                         "--play-and-exit", audio_file],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                threading.Thread(target=_play, daemon=True).start()

        if self._bubble_job:
            self.root.after_cancel(self._bubble_job)
        self._bubble_job = self.root.after(BUBBLE_DURATION, self._hide_bubble)

    def _hide_bubble(self):
        self._bubble_text = ""
        self._bubble_job  = None


def main():
    root = tk.Tk()
    app  = LofiliApp(root)

    print("Lofilia running.")
    print(f"  State file: {STATE_FILE}")
    print("  Right-click to demo states or close.")

    root.mainloop()


if __name__ == "__main__":
    main()
