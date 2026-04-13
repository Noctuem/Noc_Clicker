"""
Full-screen overlay for click-and-drag region selection.

Returns the selected region as both:
  abs_region  : {"left","top","width","height"}  (absolute pixel coords)
  rel_region  : monitor-relative dict             (see profile.py)
  monitor_info: the raw mss monitors list at capture time

Callback signature: on_select(abs_region, rel_region, monitor_info) | on_select(None, None, None)
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import mss
from PIL import Image, ImageEnhance, ImageTk

import profile as prof


class RegionSelector:
    def __init__(self, on_select: Callable):
        """
        on_select(abs_region, rel_region, monitor_info)  on success
        on_select(None, None, None)                        on cancel
        """
        self.on_select  = on_select
        self.start_x    = 0
        self.start_y    = 0
        self.rect_id    = None
        self._monitors  = None

        # Capture the entire virtual desktop
        with mss.mss() as sct:
            self._monitors  = list(sct.monitors)
            virtual = sct.monitors[0]
            self.offset_x   = virtual["left"]
            self.offset_y   = virtual["top"]
            self.total_w    = virtual["width"]
            self.total_h    = virtual["height"]
            screenshot      = sct.grab(virtual)
            self.screenshot = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

        # Dim the screenshot
        dimmed = ImageEnhance.Brightness(self.screenshot).enhance(0.45)

        # Overlay window
        self.root = tk.Toplevel()
        self.root.title("Select Region")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.geometry(
            f"{self.total_w}x{self.total_h}+{self.offset_x}+{self.offset_y}"
        )

        self.tk_image = ImageTk.PhotoImage(dimmed)
        self.canvas   = tk.Canvas(
            self.root, width=self.total_w, height=self.total_h,
            highlightthickness=0, cursor="crosshair",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)

        # Hint text
        self.canvas.create_text(
            self.total_w // 2, 20,
            text="Click and drag to select a region.  Esc to cancel.",
            fill="#cdd6f4", font=("Consolas", 13),
        )

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>",            self._on_cancel)

    # ------------------------------------------------------------------

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#cba6f7", width=2,
        )

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(
                self.rect_id, self.start_x, self.start_y, event.x, event.y
            )

    def _on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        w  = x2 - x1
        h  = y2 - y1

        self.root.destroy()

        if w > 5 and h > 5:
            abs_x = x1 + self.offset_x
            abs_y = y1 + self.offset_y
            abs_r = {"left": abs_x, "top": abs_y, "width": w, "height": h}
            rel_r = prof.region_to_relative(abs_r, self._monitors)
            self.on_select(abs_r, rel_r, self._monitors)
        else:
            self.on_select(None, None, None)

    def _on_cancel(self, event):
        self.root.destroy()
        self.on_select(None, None, None)
