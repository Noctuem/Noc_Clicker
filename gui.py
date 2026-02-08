import tkinter as tk
from tkinter import ttk

import mss
from PIL import Image, ImageTk

from region_selector import RegionSelector
from monitor import ScreenMonitor

THUMB_SIZE = (160, 120)
MARKER_SIZE = 40


class ClickMarker:
    """A small draggable on-screen crosshair showing where the auto-click will land."""

    def __init__(self, root):
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", "white")

        self.canvas = tk.Canvas(
            self.window, width=MARKER_SIZE, height=MARKER_SIZE,
            bg="white", highlightthickness=0, cursor="fleur"
        )
        self.canvas.pack()

        # Draw crosshair with circle
        mid = MARKER_SIZE // 2
        self.canvas.create_line(0, mid, MARKER_SIZE, mid, fill="red", width=2)
        self.canvas.create_line(mid, 0, mid, MARKER_SIZE, fill="red", width=2)
        self.canvas.create_oval(mid - 10, mid - 10, mid + 10, mid + 10,
                                outline="red", width=2)
        self.canvas.create_oval(mid - 2, mid - 2, mid + 2, mid + 2,
                                fill="red", outline="red")

        # Dragging state
        self._drag_x = 0
        self._drag_y = 0
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        # Start hidden
        self.window.withdraw()

    def _on_press(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        x = self.window.winfo_x() + (event.x - self._drag_x)
        y = self.window.winfo_y() + (event.y - self._drag_y)
        self.window.geometry(f"+{x}+{y}")

    def get_position(self):
        """Return the center of the marker in screen coordinates."""
        x = self.window.winfo_x() + MARKER_SIZE // 2
        y = self.window.winfo_y() + MARKER_SIZE // 2
        return (x, y)

    def show(self):
        self.window.deiconify()

    def hide(self):
        self.window.withdraw()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Auto Clicker")
        self.root.resizable(False, False)

        self.bbox = None
        self.control_image = None
        self.trigger_image = None
        self.monitor = None

        # Keep references to PhotoImage objects so they aren't garbage-collected
        self._control_photo = None
        self._trigger_photo = None

        self.click_marker = ClickMarker(root)

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

        # --- Cooldown input ---
        cooldown_frame = ttk.Frame(self.root)
        cooldown_frame.pack(fill=tk.X, **pad)
        ttk.Label(cooldown_frame, text="Cooldown (sec):").pack(side=tk.LEFT)
        self.cooldown_var = tk.StringVar(value="1.0")
        self.cooldown_entry = ttk.Entry(
            cooldown_frame, textvariable=self.cooldown_var, width=8
        )
        self.cooldown_entry.pack(side=tk.LEFT, padx=(4, 0))

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

    def _get_cooldown(self):
        try:
            val = float(self.cooldown_var.get())
            return max(0.0, val)
        except ValueError:
            return 1.0

    def _select_control(self):
        self.click_marker.hide()
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
        self.btn_toggle.config(state=tk.NORMAL)

        # Show the draggable click marker
        x, y, w, h = self.bbox
        self.click_marker.window.geometry(
            f"+{x + w // 2 - MARKER_SIZE // 2}+{y + h // 2 - MARKER_SIZE // 2}"
        )
        self.click_marker.show()
        self.status_var.set("Trigger captured. Drag the crosshair to the click target.")

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
            self.click_marker.show()
            self.status_var.set("Stopped.")
        else:
            self._start_monitor()

    def _start_monitor(self):
        if self.bbox is None or self.trigger_image is None:
            return
        click_pos = self.click_marker.get_position()
        self.click_marker.hide()
        threshold = self.threshold_var.get() / 100.0
        cooldown = self._get_cooldown()
        self.monitor = ScreenMonitor(
            bbox=self.bbox,
            trigger_image=self.trigger_image,
            click_pos=click_pos,
            threshold=threshold,
            cooldown=cooldown,
            on_status=self._on_monitor_status,
        )
        self.monitor.start()
        self.btn_toggle.config(text="Stop")
        self.btn_control.config(state=tk.DISABLED)
        self.btn_trigger.config(state=tk.DISABLED)

    def _on_monitor_status(self, msg):
        # Called from the monitor thread — schedule on the main thread
        self.root.after(0, lambda: self.status_var.set(msg))
