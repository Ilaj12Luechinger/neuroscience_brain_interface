"""
lofilia.py — Lofi Girl desktop overlay for the EEG classifier.

Run alongside eeg_classifier.ipynb:
    python lofilia.py

The overlay reads _confirmed_state from the classifier's global namespace
by importing the shared state file, OR runs standalone with a demo mode.

States:
    CALIBRATING — girl looks forward, "Calibrating..." bubble
    FOCUSED     — girl studies at desk, no bubble
    DRIFTING    — girl looks up, speech bubble with refocus/break prompt

Usage:
    1. Run eeg_classifier.ipynb in Jupyter
    2. Run: python lofilia.py
    The overlay polls state every 500ms via a shared state file (lofilia_state.txt).

To connect from the notebook, add to processing_loop after classify():
    with open("lofilia_state.txt", "w") as f:
        f.write(current_state)
"""

import tkinter as tk
import tkinter.font as tkfont
import math
import time
import os
import threading

# ── Config ─────────────────────────────────────────────────────────────────────
OVERLAY_WIDTH   = 280
OVERLAY_HEIGHT  = 320
POLL_INTERVAL   = 500   # ms between state file reads
STATE_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lofilia_state.txt")
BUBBLE_DURATION = 8000  # ms before speech bubble fades

# Colours
BG_COLOR        = "#1a1a2e"
DESK_COLOR      = "#2d2b55"
SKIN_COLOR      = "#f4c89a"
HAIR_COLOR      = "#3d2b1f"
SHIRT_COLOR     = "#6c5ce7"
BOOK_COLOR      = "#e17055"
LAMP_COLOR      = "#fdcb6e"
PLANT_COLOR     = "#00b894"
BUBBLE_BG       = "#ffffff"
BUBBLE_TEXT     = "#2d2b55"
FOCUSED_COLOR   = "#00b894"
DRIFTING_COLOR  = "#e17055"
CALIB_COLOR     = "#a0a0c0"

MESSAGES = {
    "DRIFTING": [
        "Hey, you're drifting...",
        "Want to refocus? 👀",
        "Take a 5min break?",
        "Your mind is wandering!",
        "Come back! 📚",
    ],
    "FOCUSED": [
        "Great focus! Keep it up 🎵",
        "You're in the zone!",
        "Nice work! 📖",
    ],
    "CALIBRATING": [
        "Calibrating... sit still 🎧",
        "Measuring your baseline...",
        "Just a moment...",
    ],
}

_msg_index = {"DRIFTING": 0, "FOCUSED": 0, "CALIBRATING": 0}


class LofiliApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Lofilia")
        self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+50+50")
        self.root.configure(bg=BG_COLOR)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.overrideredirect(True)   # borderless window

        # Allow dragging
        self.root.bind("<ButtonPress-1>",   self._drag_start)
        self.root.bind("<B1-Motion>",       self._drag_motion)
        self.root.bind("<ButtonPress-3>",   self._show_menu)
        self._drag_x = self._drag_y = 0

        self.canvas = tk.Canvas(
            root, width=OVERLAY_WIDTH, height=OVERLAY_HEIGHT,
            bg=BG_COLOR, highlightthickness=0
        )
        self.canvas.pack()

        self.state      = "CALIBRATING"
        self.prev_state = None
        self.bubble_job = None
        self._anim_tick = 0
        self._blink_tick = 0

        self._draw_scene()
        self._start_poll()
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
        menu.add_command(label="Close", command=self.root.destroy)
        menu.add_command(label="Demo: FOCUSED",     command=lambda: self._set_demo("FOCUSED"))
        menu.add_command(label="Demo: DRIFTING",    command=lambda: self._set_demo("DRIFTING"))
        menu.add_command(label="Demo: CALIBRATING", command=lambda: self._set_demo("CALIBRATING"))
        menu.tk_popup(e.x_root, e.y_root)

    def _set_demo(self, state):
        self.state = state

    # ── State polling ──────────────────────────────────────────────────────────
    def _start_poll(self):
        self._poll()

    def _poll(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    s = f.read().strip()
                if s in ("FOCUSED", "DRIFTING", "CALIBRATING"):
                    self.state = s
        except Exception:
            pass
        self.root.after(POLL_INTERVAL, self._poll)

    # ── Animation loop ─────────────────────────────────────────────────────────
    def _animate(self):
        self._anim_tick += 1
        self._blink_tick += 1

        # Trigger speech bubble on state change
        if self.state != self.prev_state:
            self._show_bubble()
            self.prev_state = self.state

        self._draw_scene()
        self.root.after(80, self._animate)   # ~12fps

    # ── Drawing ────────────────────────────────────────────────────────────────
    def _draw_scene(self):
        c = self.canvas
        c.delete("all")

        # Background gradient (simulated with rectangles)
        for i in range(20):
            r = int(0x1a + i * 2)
            g = int(0x1a + i * 1)
            b = int(0x2e + i * 3)
            color = f"#{r:02x}{g:02x}{b:02x}"
            c.create_rectangle(0, i * 16, OVERLAY_WIDTH, (i+1) * 16,
                                fill=color, outline="")

        # Window / moon in background
        self._draw_window()

        # Plant
        self._draw_plant()

        # Desk
        c.create_rectangle(0, 220, OVERLAY_WIDTH, 270,
                            fill=DESK_COLOR, outline="#3d3b65", width=1)

        # Lamp
        self._draw_lamp()

        # Books on desk
        self._draw_books()

        # Girl
        self._draw_girl()

        # Status indicator dot
        dot_color = {
            "FOCUSED":     FOCUSED_COLOR,
            "DRIFTING":    DRIFTING_COLOR,
            "CALIBRATING": CALIB_COLOR,
        }.get(self.state, CALIB_COLOR)
        c.create_oval(OVERLAY_WIDTH-20, 8, OVERLAY_WIDTH-8, 20,
                      fill=dot_color, outline="")

        # Speech bubble
        if hasattr(self, "_bubble_text") and self._bubble_text:
            self._draw_bubble(self._bubble_text)

        # State label at bottom
        label = self.state if self.state != "CALIBRATING" else "Calibrating..."
        c.create_text(OVERLAY_WIDTH//2, OVERLAY_HEIGHT - 12,
                      text=label, fill=dot_color,
                      font=("Courier", 9, "bold"))

    def _draw_window(self):
        c = self.canvas
        # Window frame
        c.create_rectangle(170, 20, 265, 130,
                            fill="#0f0f1a", outline="#3d3b65", width=2)
        # Moon
        t = self._anim_tick * 0.02
        moon_y = 60 + math.sin(t) * 3
        c.create_oval(195, moon_y, 225, moon_y+30,
                      fill="#fdcb6e", outline="")
        c.create_oval(205, moon_y-2, 232, moon_y+26,
                      fill="#0f0f1a", outline="")   # crescent cutout
        # Stars
        for sx, sy in [(182, 35), (245, 45), (230, 110), (178, 95), (210, 75)]:
            twinkle = 0.5 + 0.5 * math.sin(self._anim_tick * 0.1 + sx)
            bright = int(180 + 75 * twinkle)
            sc = f"#{bright:02x}{bright:02x}{bright:02x}"
            c.create_oval(sx-1, sy-1, sx+1, sy+1, fill=sc, outline="")
        # Window cross
        c.create_line(217, 20, 217, 130, fill="#3d3b65", width=1)
        c.create_line(170, 75, 265, 75,  fill="#3d3b65", width=1)

    def _draw_plant(self):
        c = self.canvas
        # Pot
        c.create_rectangle(20, 205, 50, 225, fill="#8b4513", outline="")
        # Stem
        c.create_line(35, 205, 35, 180, fill=PLANT_COLOR, width=2)
        # Leaves — sway slightly when focused
        sway = math.sin(self._anim_tick * 0.05) * 3 if self.state == "FOCUSED" else 0
        for lx, ly, r in [(25+sway, 185, 12), (45-sway, 175, 10), (30+sway, 168, 9)]:
            c.create_oval(lx-r, ly-r//2, lx+r, ly+r//2,
                          fill=PLANT_COLOR, outline="")

    def _draw_lamp(self):
        c = self.canvas
        # Lamp arm
        c.create_line(130, 220, 130, 175, fill="#888", width=3)
        c.create_line(130, 175, 155, 165, fill="#888", width=3)
        # Lampshade
        c.create_polygon(145, 165, 165, 165, 170, 180, 140, 180,
                         fill=LAMP_COLOR, outline="#e0a040")
        # Light cone when focused
        if self.state in ("FOCUSED",):
            alpha_steps = 6
            for i in range(alpha_steps):
                spread = 30 + i * 12
                ya = 180 + i * 8
                brightness = int(60 - i * 8)
                lc = f"#{brightness+140:02x}{brightness+120:02x}{brightness:02x}"
                c.create_polygon(
                    155 - spread//2, ya,
                    155 + spread//2, ya,
                    155 + spread//2 + 5, ya + 10,
                    155 - spread//2 - 5, ya + 10,
                    fill=lc, outline="", stipple=""
                )

    def _draw_books(self):
        c = self.canvas
        colors = ["#e17055", "#6c5ce7", "#00b894", "#fd79a8"]
        for i, col in enumerate(colors):
            x = 60 + i * 14
            c.create_rectangle(x, 200, x+12, 222, fill=col, outline="#222")

    def _draw_girl(self):
        c = self.canvas
        t    = self._anim_tick
        blink = (t % 40) < 3   # blink every ~3 seconds

        # Breathing bob
        bob = math.sin(t * 0.04) * 1.5
        base_y = 140 + bob

        if self.state == "DRIFTING":
            # Head tilted up, looking away
            head_x, head_y = 110, base_y - 15
            body_tilt = -8
        else:
            # Head down studying
            head_x, head_y = 105, base_y
            body_tilt = 0

        # Body / torso
        c.create_rectangle(85, base_y+30, 130, base_y+80,
                            fill=SHIRT_COLOR, outline="")

        # Arm on desk
        if self.state != "DRIFTING":
            c.create_rectangle(90, base_y+60, 145, base_y+75,
                                fill=SKIN_COLOR, outline="")

        # Head
        c.create_oval(head_x-18, head_y-20, head_x+18, head_y+18,
                      fill=SKIN_COLOR, outline="")

        # Hair
        c.create_arc(head_x-20, head_y-28, head_x+20, head_y+5,
                     start=0, extent=180, fill=HAIR_COLOR, outline="")
        # Hair sides
        c.create_oval(head_x-22, head_y-15, head_x-10, head_y+10,
                      fill=HAIR_COLOR, outline="")
        c.create_oval(head_x+8, head_y-15, head_x+22, head_y+10,
                      fill=HAIR_COLOR, outline="")

        # Eyes
        if self.state == "DRIFTING":
            # Eyes open wide, looking up
            ey = head_y - 4
            if not blink:
                c.create_oval(head_x-8, ey-4, head_x-2, ey+4, fill="#3d2b1f", outline="")
                c.create_oval(head_x+2, ey-4, head_x+8, ey+4, fill="#3d2b1f", outline="")
                # Eyebrows raised
                c.create_line(head_x-9, ey-7, head_x-2, ey-9, fill=HAIR_COLOR, width=2)
                c.create_line(head_x+2, ey-9, head_x+9, ey-7, fill=HAIR_COLOR, width=2)
            else:
                c.create_line(head_x-8, ey, head_x-2, ey, fill="#3d2b1f", width=2)
                c.create_line(head_x+2, ey, head_x+8, ey, fill="#3d2b1f", width=2)
        else:
            # Eyes looking down (studying)
            ey = head_y
            if not blink:
                c.create_arc(head_x-8, ey-3, head_x-2, ey+5,
                             start=200, extent=140, fill="#3d2b1f", outline="")
                c.create_arc(head_x+2, ey-3, head_x+8, ey+5,
                             start=200, extent=140, fill="#3d2b1f", outline="")
            else:
                c.create_line(head_x-8, ey+1, head_x-2, ey+1, fill="#3d2b1f", width=2)
                c.create_line(head_x+2, ey+1, head_x+8, ey+1, fill="#3d2b1f", width=2)

        # Headphones
        c.create_arc(head_x-20, head_y-22, head_x+20, head_y+5,
                     start=20, extent=140, style="arc",
                     outline="#555", width=3)
        c.create_oval(head_x-22, head_y-10, head_x-14, head_y+2,
                      fill="#444", outline="")
        c.create_oval(head_x+14, head_y-10, head_x+22, head_y+2,
                      fill="#444", outline="")

        # Book / notebook on desk
        if self.state != "DRIFTING":
            c.create_rectangle(95, base_y+72, 160, base_y+82,
                                fill=BOOK_COLOR, outline="#c0392b")
            # Page lines
            for lx in range(100, 158, 8):
                c.create_line(lx, base_y+74, lx, base_y+80,
                               fill="#c0392b", width=1)

        # Calibration spinner
        if self.state == "CALIBRATING":
            angle = (t * 6) % 360
            r = 12
            cx, cy = OVERLAY_WIDTH - 35, OVERLAY_HEIGHT - 35
            x1 = cx + r * math.cos(math.radians(angle))
            y1 = cy + r * math.sin(math.radians(angle))
            x2 = cx + r * math.cos(math.radians(angle + 180))
            y2 = cy + r * math.sin(math.radians(angle + 180))
            c.create_line(x1, y1, x2, y2, fill=CALIB_COLOR, width=2)

    def _draw_bubble(self, text: str):
        c = self.canvas
        # Bubble position
        bx, by = 10, 10
        bw, bh = 160, 50
        r = 10
        # Rounded rect
        c.create_rectangle(bx+r, by, bx+bw-r, by+bh, fill=BUBBLE_BG, outline="")
        c.create_rectangle(bx, by+r, bx+bw, by+bh-r, fill=BUBBLE_BG, outline="")
        c.create_oval(bx, by, bx+2*r, by+2*r, fill=BUBBLE_BG, outline="")
        c.create_oval(bx+bw-2*r, by, bx+bw, by+2*r, fill=BUBBLE_BG, outline="")
        c.create_oval(bx, by+bh-2*r, bx+2*r, by+bh, fill=BUBBLE_BG, outline="")
        c.create_oval(bx+bw-2*r, by+bh-2*r, bx+bw, by+bh, fill=BUBBLE_BG, outline="")
        # Tail pointing to girl
        c.create_polygon(80, by+bh, 95, by+bh, 90, by+bh+12,
                         fill=BUBBLE_BG, outline="")
        # Text
        c.create_text(bx + bw//2, by + bh//2,
                      text=text, fill=BUBBLE_TEXT,
                      font=("Courier", 9, "bold"),
                      width=bw - 10, justify="center")

    # ── Speech bubble trigger ──────────────────────────────────────────────────
    def _show_bubble(self):
        msgs = MESSAGES.get(self.state, [])
        if not msgs:
            self._bubble_text = ""
            return
        idx = _msg_index[self.state] % len(msgs)
        self._bubble_text = msgs[idx]
        _msg_index[self.state] = idx + 1

        if self.bubble_job:
            self.root.after_cancel(self.bubble_job)
        self.bubble_job = self.root.after(BUBBLE_DURATION, self._hide_bubble)

    def _hide_bubble(self):
        self._bubble_text = ""
        self.bubble_job = None


def main():
    root = tk.Tk()
    app  = LofiliApp(root)
    app._bubble_text = ""

    print("Lofilia running.")
    print("  Right-click to demo states or close.")
    print(f"  Reading state from: {os.path.abspath(STATE_FILE)}")
    print()
    print("  To connect from eeg_classifier.ipynb, add after classify():")
    print('  with open("lofilia_state.txt", "w") as f: f.write(current_state)')

    root.mainloop()


if __name__ == "__main__":
    main()
