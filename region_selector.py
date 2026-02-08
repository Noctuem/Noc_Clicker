import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance
import mss


class RegionSelector:
    """Fullscreen overlay that lets the user draw a rectangle to select a screen region."""

    def __init__(self, on_select=None):
        """
        Args:
            on_select: callback(bbox) where bbox is (x, y, width, height) in absolute
                       screen coordinates, or None if cancelled.
        """
        self.on_select = on_select
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        # Capture the entire virtual desktop
        with mss.mss() as sct:
            # monitor 0 is the combined virtual screen
            virtual = sct.monitors[0]
            self.offset_x = virtual["left"]
            self.offset_y = virtual["top"]
            self.total_w = virtual["width"]
            self.total_h = virtual["height"]
            screenshot = sct.grab(virtual)
            self.screenshot = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

        # Dim the screenshot
        dimmed = ImageEnhance.Brightness(self.screenshot).enhance(0.5)

        # Build the overlay window
        self.root = tk.Toplevel()
        self.root.title("Select Region")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.geometry(
            f"{self.total_w}x{self.total_h}+{self.offset_x}+{self.offset_y}"
        )

        self.tk_image = ImageTk.PhotoImage(dimmed)
        self.canvas = tk.Canvas(
            self.root, width=self.total_w, height=self.total_h,
            highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)

        # Bind events
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", self._on_cancel)

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=2
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
        w = x2 - x1
        h = y2 - y1

        self.root.destroy()

        if w > 5 and h > 5:
            # Convert canvas coords to absolute screen coords
            abs_x = x1 + self.offset_x
            abs_y = y1 + self.offset_y
            if self.on_select:
                self.on_select((abs_x, abs_y, w, h))
        else:
            if self.on_select:
                self.on_select(None)

    def _on_cancel(self, event):
        self.root.destroy()
        if self.on_select:
            self.on_select(None)
