import tkinter as tk
from tkinter import ttk

import mss
from PIL import Image, ImageTk

from region_selector import RegionSelector, ClickPositionSelector
from monitor import ScreenMonitor

THUMB_SIZE = (160, 120)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Auto Clicker")
        self.root.resizable(False, False)

        self.bbox = None
        self.click_pos = None
        self.control_image = None
        self.trigger_image = None
        self.monitor = None

        # Keep references to PhotoImage objects so they aren't garbage-collected
        self._control_photo = None
        self._trigger_photo = None

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- Buttons ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, **pad)

        self.btn_control = ttk.Button(
            btn_frame, text="Select Region & Capture Control",
            command=self._select_control
        )
        self.btn_control.pack(fill=tk.X, **pad)

        self.btn_trigger = ttk.Button(
            btn_frame, text="Capture Trigger", state=tk.DISABLED,
            command=self._capture_trigger
        )
        self.btn_trigger.pack(fill=tk.X, **pad)

        self.btn_click_pos = ttk.Button(
            btn_frame, text="Set Click Position", state=tk.DISABLED,
            command=self._select_click_pos
        )
        self.btn_click_pos.pack(fill=tk.X, **pad)

        # --- Threshold slider ---
        slider_frame = ttk.Frame(self.root)
        slider_frame.pack(fill=tk.X, **pad)
        ttk.Label(slider_frame, text="Similarity Threshold:").pack(side=tk.LEFT)
        self.threshold_var = tk.IntVar(value=90)
        self.slider = ttk.Scale(
            slider_frame, from_=50, to=100, variable=self.threshold_var,
            orient=tk.HORIZONTAL
        )
        self.slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self.threshold_label = ttk.Label(slider_frame, text="90%")
        self.threshold_label.pack(side=tk.LEFT, padx=(4, 0))
        self.threshold_var.trace_add("write", self._update_threshold_label)

        # --- Cooldown slider ---
        cooldown_frame = ttk.Frame(self.root)
        cooldown_frame.pack(fill=tk.X, **pad)
        ttk.Label(cooldown_frame, text="Cooldown (sec):").pack(side=tk.LEFT)
        self.cooldown_var = tk.DoubleVar(value=1.0)
        self.cooldown_slider = ttk.Scale(
            cooldown_frame, from_=0.1, to=10.0, variable=self.cooldown_var,
            orient=tk.HORIZONTAL
        )
        self.cooldown_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self.cooldown_label = ttk.Label(cooldown_frame, text="1.0s")
        self.cooldown_label.pack(side=tk.LEFT, padx=(4, 0))
        self.cooldown_var.trace_add("write", self._update_cooldown_label)

        # --- Start / Stop ---
        self.btn_toggle = ttk.Button(
            self.root, text="Start", state=tk.DISABLED,
            command=self._toggle_monitor
        )
        self.btn_toggle.pack(fill=tk.X, **pad)

        # --- Status ---
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(self.root, textvariable=self.status_var,
                  foreground="gray").pack(**pad)

        # --- Previews ---
        preview_frame = ttk.Frame(self.root)
        preview_frame.pack(fill=tk.X, **pad)

        ctrl_frame = ttk.LabelFrame(preview_frame, text="Control")
        ctrl_frame.pack(side=tk.LEFT, padx=4)
        self.control_preview = ttk.Label(ctrl_frame)
        self.control_preview.pack(padx=4, pady=4)

        trig_frame = ttk.LabelFrame(preview_frame, text="Trigger")
        trig_frame.pack(side=tk.LEFT, padx=4)
        self.trigger_preview = ttk.Label(trig_frame)
        self.trigger_preview.pack(padx=4, pady=4)

    def _update_threshold_label(self, *_args):
        self.threshold_label.config(text=f"{self.threshold_var.get()}%")

    def _update_cooldown_label(self, *_args):
        self.cooldown_label.config(text=f"{self.cooldown_var.get():.1f}s")

    def _select_control(self):
        self.root.withdraw()
        # Small delay so the main window has time to hide
        self.root.after(200, self._open_selector)

    def _open_selector(self):
        RegionSelector(on_select=self._on_region_selected)

    def _on_region_selected(self, bbox):
        self.root.deiconify()
        if bbox is None:
            self.status_var.set("Selection cancelled.")
            return

        self.bbox = bbox
        self.control_image = self._capture_region(bbox)
        self._show_preview(self.control_image, "control")
        self.btn_trigger.config(state=tk.NORMAL)
        self.status_var.set(f"Control captured.  Region: {bbox}")

    def _capture_trigger(self):
        if self.bbox is None:
            return
        self.trigger_image = self._capture_region(self.bbox)
        self._show_preview(self.trigger_image, "trigger")
        self.btn_click_pos.config(state=tk.NORMAL)
        self.status_var.set("Trigger captured. Now set the click position.")

    def _select_click_pos(self):
        self.root.withdraw()
        self.root.after(200, self._open_click_selector)

    def _open_click_selector(self):
        ClickPositionSelector(on_select=self._on_click_pos_selected)

    def _on_click_pos_selected(self, pos):
        self.root.deiconify()
        if pos is None:
            self.status_var.set("Click position selection cancelled.")
            return
        self.click_pos = pos
        self.btn_toggle.config(state=tk.NORMAL)
        self.status_var.set(f"Click position set at ({pos[0]}, {pos[1]}). Ready to start.")

    def _capture_region(self, bbox):
        x, y, w, h = bbox
        with mss.mss() as sct:
            shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
            return Image.frombytes("RGB", shot.size, shot.rgb)

    def _show_preview(self, image, which):
        thumb = image.copy()
        thumb.thumbnail(THUMB_SIZE)
        photo = ImageTk.PhotoImage(thumb)
        if which == "control":
            self._control_photo = photo
            self.control_preview.config(image=photo)
        else:
            self._trigger_photo = photo
            self.trigger_preview.config(image=photo)

    def _toggle_monitor(self):
        if self.monitor and self.monitor._running:
            self.monitor.stop()
            self.btn_toggle.config(text="Start")
            self.btn_control.config(state=tk.NORMAL)
            self.btn_trigger.config(state=tk.NORMAL)
            self.btn_click_pos.config(state=tk.NORMAL)
            self.status_var.set("Stopped.")
        else:
            self._start_monitor()

    def _start_monitor(self):
        if self.bbox is None or self.trigger_image is None or self.click_pos is None:
            return
        threshold = self.threshold_var.get() / 100.0
        cooldown = self.cooldown_var.get()
        self.monitor = ScreenMonitor(
            bbox=self.bbox,
            trigger_image=self.trigger_image,
            click_pos=self.click_pos,
            threshold=threshold,
            cooldown=cooldown,
            on_status=self._on_monitor_status,
        )
        self.monitor.start()
        self.btn_toggle.config(text="Stop")
        self.btn_control.config(state=tk.DISABLED)
        self.btn_trigger.config(state=tk.DISABLED)
        self.btn_click_pos.config(state=tk.DISABLED)

    def _on_monitor_status(self, msg):
        # Called from the monitor thread — schedule on the main thread
        self.root.after(0, lambda: self.status_var.set(msg))
