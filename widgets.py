"""
Custom tkinter widgets used throughout Noc Clicker.

BindingBox      – shows a binding, click to capture new one (keyboard or mouse)
ColorSwatch     – coloured square; click opens ColorPickerDialog
ColorPickerDialog – HSV wheel + RGBA sliders
RegionPreview   – thumbnail of a captured screen region
WindowDropdown  – combobox of visible windows with a refresh button
TargetItem      – one row in the target list (advanced mode)
TargetList      – scrollable list of TargetItems
"""

from __future__ import annotations

import colorsys
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageTk

import actions
from assets import FONT_FAMILY
import hotkey as hk
import window_manager as wm

THUMB = (148, 100)


# ===========================================================================
# BindingBox
# ===========================================================================

class BindingBox(ttk.Frame):
    """
    Displays the current binding.  Click → enters listening mode; next key or
    (optionally) mouse button press becomes the new binding.

    Parameters
    ----------
    parent          – parent widget
    allow_mouse     – if True, mouse buttons are also accepted as bindings
    on_change       – callback(binding_dict) fired on every update
    theme_manager   – ThemeManager instance for colour access
    """

    def __init__(
        self,
        parent,
        allow_mouse: bool = False,
        on_change: Optional[Callable] = None,
        theme_manager=None,
        hotkey_manager=None,
        **kw,
    ):
        super().__init__(parent, style="Card.TFrame", **kw)
        self._allow_mouse   = allow_mouse
        self._on_change     = on_change
        self._tm            = theme_manager
        self._hm            = hotkey_manager
        self._binding: Optional[dict] = None
        self._listening     = False
        self._capture: Optional[hk.BindingCapture] = None
        self._mouse_binds   = []

        self._var = tk.StringVar(value="Unbound")
        self._lbl = ttk.Label(
            self, textvariable=self._var,
            style="Card.TLabel", anchor="center", cursor="hand2",
            padding=(8, 4),
        )
        self._lbl.pack(fill=tk.BOTH, expand=True)
        self._lbl.bind("<Button-1>", self._start_listen)

    # ------------------------------------------------------------------

    def set_binding(self, b: Optional[dict]) -> None:
        self._binding = b
        self._var.set(actions.binding_label(b))
        self._listening = False

    def get_binding(self) -> Optional[dict]:
        return self._binding

    def _start_listen(self, _event=None) -> None:
        if self._listening:
            return
        # Pause hotkey manager so the existing binding doesn't fire while capturing
        if self._hm:
            self._hm.pause()
        self._listening = True
        self._var.set("Press a key or click…" if self._allow_mouse else "Press a key…")

        if self._allow_mouse:
            self._bind_mouse()

        self._capture = hk.BindingCapture()
        self._capture.start(self._on_key_captured, on_cancel=self._on_capture_cancelled)

    def _bind_mouse(self) -> None:
        def make_handler(btn):
            def handler(event):
                if self._listening:
                    self._cancel_capture()
                    b = actions.make_binding("click", button=btn)
                    self._apply_binding(b)
            return handler

        root = self.winfo_toplevel()
        for btn, name in [("<Button-1>", "left"), ("<Button-2>", "middle"), ("<Button-3>", "right")]:
            tag = root.bind(btn, make_handler(name), add="+")
            self._mouse_binds.append((root, btn, tag))

    def _unbind_mouse(self) -> None:
        for root, btn, _tag in self._mouse_binds:
            try:
                root.unbind(btn)
            except Exception:
                pass
        self._mouse_binds.clear()

    def _on_key_captured(self, mods: list, vk: int, key_name: str) -> None:
        self._unbind_mouse()
        b = actions.make_binding("key", mods=mods, key=key_name, vk=vk)
        # Schedule UI update on main thread
        self.after(0, lambda: self._apply_binding(b))

    def _on_capture_cancelled(self) -> None:
        """Called (from daemon thread) when Escape was pressed during capture."""
        self.after(0, self._restore_after_cancel)

    def _restore_after_cancel(self) -> None:
        """Restore label to previous binding and resume hotkeys."""
        self._listening = False
        self._unbind_mouse()
        self._capture = None
        self._var.set(actions.binding_label(self._binding))  # restores "Unbound" if None
        if self._hm:
            self._hm.resume()

    def _cancel_capture(self) -> None:
        if self._capture:
            self._capture.cancel()
            self._capture = None
        self._unbind_mouse()
        self._listening = False
        if self._hm:
            self._hm.resume()

    def _apply_binding(self, b: dict) -> None:
        self._listening = False
        self._binding   = b
        self._var.set(actions.binding_label(b))
        if self._hm:
            self._hm.resume()
        if self._on_change:
            self._on_change(b)


# ===========================================================================
# ColorSwatch + ColorPickerDialog
# ===========================================================================

_WHEEL_SIZE = 180
_WHEEL_IMAGE: Optional[Image.Image] = None


def _build_wheel() -> Image.Image:
    global _WHEEL_IMAGE
    if _WHEEL_IMAGE is not None:
        return _WHEEL_IMAGE
    size = _WHEEL_SIZE
    r    = size // 2
    y, x = np.mgrid[-r:r, -r:r].astype(np.float32)
    dist  = np.sqrt(x**2 + y**2)
    angle = np.arctan2(y, x)
    mask  = dist <= r

    h = ((angle + np.pi) / (2 * np.pi))
    s = np.clip(dist / r, 0, 1)
    v = np.ones_like(h)

    # Vectorised HSV → RGB
    hi   = (h * 6).astype(np.int32) % 6
    f    = h * 6 - np.floor(h * 6)
    p    = v * (1 - s)
    q    = v * (1 - f * s)
    t_   = v * (1 - (1 - f) * s)

    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    for ch, pairs in enumerate([
        (v, q, p, p, t_, v),
        (t_, v, v, q, p, p),
        (p, p, t_, v, v, q),
    ]):
        chan = np.select(
            [hi == i for i in range(6)],
            [pairs[i] for i in range(6)],
        )
        rgb[:, :, ch] = (chan * 255).astype(np.uint8)

    # Apply mask (outside circle = bg)
    bg = 30
    for ch in range(3):
        rgb[:, :, ch] = np.where(mask, rgb[:, :, ch], bg)

    _WHEEL_IMAGE = Image.fromarray(rgb, "RGB")
    return _WHEEL_IMAGE


class ColorPickerDialog(tk.Toplevel):
    """Modal HSV wheel + alpha slider colour picker."""

    def __init__(self, parent, initial: str = "#cba6f7", title: str = "Pick a colour"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._result: Optional[str] = None
        self._r = self._g = self._b = 0
        self._a = 255

        self._parse_hex(initial)

        self._build_ui()
        self._refresh_all()

        self.wait_window()

    # ------------------------------------------------------------------

    def _parse_hex(self, hex_str: str) -> None:
        h = hex_str.lstrip("#")
        if len(h) == 8:
            self._r, self._g, self._b, self._a = (int(h[i:i+2], 16) for i in (0,2,4,6))
        elif len(h) == 6:
            self._r, self._g, self._b = (int(h[i:i+2], 16) for i in (0,2,4))
            self._a = 255
        else:
            self._r = self._g = self._b = 128
            self._a = 255

    def _to_hex(self) -> str:
        if self._a < 255:
            return f"#{self._r:02x}{self._g:02x}{self._b:02x}{self._a:02x}"
        return f"#{self._r:02x}{self._g:02x}{self._b:02x}"

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        f   = FONT_FAMILY

        # Wheel canvas
        self._wheel_img = _build_wheel()
        self._wheel_tk  = ImageTk.PhotoImage(self._wheel_img)
        self._canvas    = tk.Canvas(
            self, width=_WHEEL_SIZE, height=_WHEEL_SIZE,
            highlightthickness=0, cursor="crosshair",
        )
        self._canvas.grid(row=0, column=0, columnspan=2, **pad)
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._wheel_tk)
        self._marker = self._canvas.create_oval(0, 0, 0, 0, outline="white", width=2)
        self._canvas.bind("<Button-1>",  self._wheel_click)
        self._canvas.bind("<B1-Motion>", self._wheel_click)

        # Sliders: R G B A + Value
        slider_frame = ttk.Frame(self)
        slider_frame.grid(row=1, column=0, columnspan=2, **pad)

        self._sliders = {}
        self._slider_vars = {}
        for i, (label, attr, max_val) in enumerate([
            ("R", "_r", 255), ("G", "_g", 255), ("B", "_b", 255),
            ("A", "_a", 255), ("V", None, 100),
        ]):
            var = tk.IntVar(value=getattr(self, attr) if attr else 100)
            self._slider_vars[label] = var

            ttk.Label(slider_frame, text=label, font=(f, 9), width=2).grid(
                row=i, column=0, sticky="e", padx=(0, 4)
            )
            s = ttk.Scale(slider_frame, from_=0, to=max_val, variable=var,
                          orient=tk.HORIZONTAL, length=200)
            s.grid(row=i, column=1, padx=4)
            val_lbl = ttk.Label(slider_frame, text=str(var.get()), width=4, font=(f, 9))
            val_lbl.grid(row=i, column=2)
            self._sliders[label] = (s, val_lbl)

            def _on_change(_, lbl=label, v=var, a=attr, vl=val_lbl):
                vl.config(text=str(v.get()))
                if a:
                    setattr(self, a, v.get())
                self._refresh_from_sliders(lbl)

            var.trace_add("write", _on_change)

        # Hex entry
        hex_frame = ttk.Frame(self)
        hex_frame.grid(row=2, column=0, columnspan=2, **pad)
        ttk.Label(hex_frame, text="#", font=(f, 10)).pack(side=tk.LEFT)
        self._hex_var = tk.StringVar()
        self._hex_entry = ttk.Entry(hex_frame, textvariable=self._hex_var, width=10, font=(f, 10))
        self._hex_entry.pack(side=tk.LEFT, padx=4)
        self._hex_entry.bind("<Return>", self._hex_entered)

        # Preview
        self._preview = tk.Label(self, width=6, height=2, relief="flat")
        self._preview.grid(row=2, column=1, padx=8, pady=4, sticky="e")

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(btn_frame, text="OK",     style="Accent.TButton",
                   command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

    def _refresh_from_sliders(self, changed: str) -> None:
        if changed in ("R", "G", "B"):
            pass  # self._r/_g/_b already updated by trace
        elif changed == "A":
            pass  # self._a already updated
        elif changed == "V":
            v = self._slider_vars["V"].get() / 100.0
            h, s, _ = colorsys.rgb_to_hsv(self._r/255, self._g/255, self._b/255)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            self._r, self._g, self._b = int(r*255), int(g*255), int(b*255)
        self._refresh_all()

    def _wheel_click(self, event) -> None:
        r = _WHEEL_SIZE // 2
        dx = event.x - r
        dy = event.y - r
        dist = (dx**2 + dy**2) ** 0.5
        if dist > r:
            return
        h = (np.arctan2(dy, dx) + np.pi) / (2 * np.pi)
        s = dist / r
        v = self._slider_vars["V"].get() / 100.0
        rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
        self._r, self._g, self._b = int(rr*255), int(gg*255), int(bb*255)
        self._refresh_all()

    def _refresh_all(self) -> None:
        for lbl, attr in [("R", "_r"), ("G", "_g"), ("B", "_b"), ("A", "_a")]:
            v = getattr(self, attr)
            self._slider_vars[lbl].set(v)

        h, s, v_val = colorsys.rgb_to_hsv(self._r/255, self._g/255, self._b/255)
        self._slider_vars["V"].set(int(v_val * 100))

        # Update wheel marker position
        r = _WHEEL_SIZE // 2
        mx = int(r + s * r * np.cos(h * 2 * np.pi - np.pi))
        my = int(r + s * r * np.sin(h * 2 * np.pi - np.pi))
        d = 5
        self._canvas.coords(self._marker, mx-d, my-d, mx+d, my+d)

        hex_str = self._to_hex()
        self._hex_var.set(hex_str.lstrip("#"))
        self._preview.config(bg=f"#{self._r:02x}{self._g:02x}{self._b:02x}")

    def _hex_entered(self, _event=None) -> None:
        raw = self._hex_var.get().strip().lstrip("#")
        try:
            self._parse_hex(raw)
            self._refresh_all()
        except ValueError:
            pass

    def _ok(self) -> None:
        self._result = self._to_hex()
        self.destroy()

    @classmethod
    def ask(cls, parent, initial: str = "#cba6f7", title: str = "Pick a colour") -> Optional[str]:
        dlg = cls(parent, initial, title)
        return dlg._result


class ColorSwatch(tk.Label):
    """Coloured square that opens the colour picker on click."""

    def __init__(self, parent, color: str = "#cba6f7",
                 on_change: Optional[Callable] = None, size: int = 20, **kw):
        super().__init__(parent, bg=color, width=2, height=1,
                         relief="solid", cursor="hand2", **kw)
        self._color     = color
        self._on_change = on_change
        self.bind("<Button-1>", self._click)

    def get_color(self) -> str:
        return self._color

    def set_color(self, c: str) -> None:
        self._color = c
        self.config(bg=c)

    def _click(self, _event=None) -> None:
        result = ColorPickerDialog.ask(self, initial=self._color)
        if result:
            self.set_color(result)
            if self._on_change:
                self._on_change(result)


# ===========================================================================
# RegionPreview
# ===========================================================================

class RegionPreview(ttk.Label):
    """Thumbnail label for a captured region image."""

    def __init__(self, parent, size: tuple = THUMB, **kw):
        super().__init__(parent, **kw)
        self._size  = size
        self._photo = None
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        img = Image.new("RGB", self._size, (49, 50, 68))
        self._photo = ImageTk.PhotoImage(img)
        self.config(image=self._photo)

    def set_image(self, img: Optional[Image.Image]) -> None:
        if img is None:
            self._show_placeholder()
            return
        thumb = img.copy()
        thumb.thumbnail(self._size)
        bg = Image.new("RGB", self._size, (49, 50, 68))
        x = (self._size[0] - thumb.width) // 2
        y = (self._size[1] - thumb.height) // 2
        bg.paste(thumb, (x, y))
        self._photo = ImageTk.PhotoImage(bg)
        self.config(image=self._photo)


# ===========================================================================
# WindowDropdown
# ===========================================================================

class WindowDropdown(ttk.Frame):
    """
    Combobox listing visible windows + a refresh button.
    Value is (hwnd, title) or (None, "Any window").
    """

    ANY = (None, "Any window")

    def __init__(self, parent, on_change: Optional[Callable] = None, **kw):
        super().__init__(parent, style="Card.TFrame", **kw)
        self._on_change = on_change
        self._windows: list[tuple] = [self.ANY]
        self._var = tk.StringVar(value="Any window")

        self._combo = ttk.Combobox(
            self, textvariable=self._var, state="readonly", width=26,
        )
        self._combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self._combo.bind("<<ComboboxSelected>>", self._on_select)

        self._btn = ttk.Button(self, text="⟳", width=3,
                               style="Icon.TButton", command=self.refresh)
        self._btn.pack(side=tk.LEFT)
        self.refresh()

    def refresh(self) -> None:
        wins = wm.get_all_windows()
        self._windows = [self.ANY] + [(hwnd, t) for hwnd, t in wins]
        self._combo["values"] = [t for _, t in self._windows]
        current = self._var.get()
        if current not in [t for _, t in self._windows]:
            self._var.set("Any window")

    def get_hwnd(self) -> Optional[int]:
        title = self._var.get()
        for hwnd, t in self._windows:
            if t == title:
                return hwnd
        return None

    def set_hwnd(self, hwnd: Optional[int]) -> None:
        for h, t in self._windows:
            if h == hwnd:
                self._var.set(t)
                return
        self._var.set("Any window")

    def _on_select(self, _event=None) -> None:
        if self._on_change:
            self._on_change(self.get_hwnd())


# ===========================================================================
# TargetItem  (used in advanced mode target list)
# ===========================================================================

class TargetItem(ttk.Frame):
    """
    One target row.  Shows name, trigger source, pre-condition, action, window, cooldown.
    Emits callbacks for reorder requests and deletion.
    """

    def __init__(
        self,
        parent,
        target_id:    str,
        index:        int,
        adv_mode:     str,           # "sequence" | "parallel"
        other_targets: list[tuple],  # [(id, name), ...]  for link dropdown
        on_move_up:   Callable,
        on_move_down: Callable,
        on_delete:    Callable,
        on_change:    Callable,      # called whenever anything changes
        theme_manager=None,
        hotkey_manager=None,
        **kw,
    ):
        super().__init__(parent, style="Card.TFrame", **kw)
        self._id         = target_id
        self._index      = index
        self._adv_mode   = adv_mode
        self._on_move_up = on_move_up
        self._on_move_dn = on_move_down
        self._on_delete  = on_delete
        self._on_change  = on_change
        self._tm         = theme_manager
        self._hm         = hotkey_manager

        self._build()

    # ------------------------------------------------------------------

    def _build(self):
        f = FONT_FAMILY
        self.columnconfigure(1, weight=1)

        # --- Header row ---
        hdr = ttk.Frame(self, style="Card.TFrame")
        hdr.grid(row=0, column=0, columnspan=3, sticky="ew", padx=4, pady=(4, 0))

        self._name_var = tk.StringVar(value=f"Target {self._index + 1}")
        name_entry = ttk.Entry(hdr, textvariable=self._name_var, width=18, font=(f, 9))
        name_entry.pack(side=tk.LEFT, padx=(0, 6))
        self._name_var.trace_add("write", lambda *_: self._on_change())

        ttk.Button(hdr, text="▲", width=2, style="Icon.TButton",
                   command=self._on_move_up).pack(side=tk.LEFT, padx=1)
        ttk.Button(hdr, text="▼", width=2, style="Icon.TButton",
                   command=self._on_move_dn).pack(side=tk.LEFT, padx=1)
        ttk.Button(hdr, text="✕", width=2, style="Icon.TButton",
                   command=lambda: self._on_delete(self._id)).pack(side=tk.RIGHT, padx=1)

        # --- Trigger source (parallel only) ---
        if self._adv_mode == "parallel":
            ts_frame = ttk.Frame(self, style="Card.TFrame")
            ts_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=2)
            ttk.Label(ts_frame, text="Trigger:", style="Card.Small.TLabel").pack(side=tk.LEFT)

            self._trigger_src_var = tk.StringVar(value="own")
            ttk.Radiobutton(ts_frame, text="Own region", variable=self._trigger_src_var,
                            value="own", style="Card.TRadiobutton",
                            command=self._on_change).pack(side=tk.LEFT, padx=(4, 8))

            self._link_var = tk.StringVar(value="")
            self._link_combo = ttk.Combobox(ts_frame, textvariable=self._link_var,
                                             state="readonly", width=14)
            self._link_combo.bind("<<ComboboxSelected>>", lambda _: (
                self._trigger_src_var.set("link"), self._on_change()
            ))
            self._link_combo.pack(side=tk.LEFT)
        else:
            self._trigger_src_var = None

        # --- Pre-condition (sequence only) ---
        if self._adv_mode == "sequence":
            pc_frame = ttk.Frame(self, style="Card.TFrame")
            pc_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=4, pady=2)
            ttk.Label(pc_frame, text="Wait:", style="Card.Small.TLabel").pack(side=tk.LEFT)
            self._cond_var = tk.StringVar(value="immediate")
            cond_opts = ["immediate", "wait_time", "wait_primary", "wait_trigger"]
            cond_labels = ["Nothing (immediate)", "Time", "Primary trigger again", "New trigger image"]
            self._cond_combo = ttk.Combobox(pc_frame, textvariable=self._cond_var,
                                             values=cond_labels, state="readonly", width=22)
            self._cond_combo.current(0)
            self._cond_combo.pack(side=tk.LEFT, padx=(4, 8))
            self._cond_combo.bind("<<ComboboxSelected>>", lambda _: (
                self._cond_var.set(cond_opts[self._cond_combo.current()]),
                self._show_cond_extra(),
                self._on_change(),
            ))

            self._wait_secs_var = tk.StringVar(value="1.0")
            self._wait_secs_entry = ttk.Entry(pc_frame, textvariable=self._wait_secs_var, width=6)
            self._wait_secs_entry.pack(side=tk.LEFT)
            ttk.Label(pc_frame, text="s", style="Card.Muted.TLabel").pack(side=tk.LEFT, padx=(2,0))
            self._wait_secs_entry.pack_forget()
            self._wait_secs_var.trace_add("write", lambda *_: self._on_change())
        else:
            self._cond_var = None

        # --- Action ---
        act_frame = ttk.Frame(self, style="Card.TFrame")
        act_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=4, pady=2)
        ttk.Label(act_frame, text="Action:", style="Card.Small.TLabel").pack(side=tk.LEFT)
        self._binding_box = BindingBox(
            act_frame, allow_mouse=True,
            on_change=lambda _: self._on_change(),
            theme_manager=self._tm,
            hotkey_manager=self._hm,
        )
        self._binding_box.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        # --- Target window ---
        win_frame = ttk.Frame(self, style="Card.TFrame")
        win_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=4, pady=2)
        ttk.Label(win_frame, text="Window:", style="Card.Small.TLabel").pack(side=tk.LEFT)
        self._window_dd = WindowDropdown(win_frame, on_change=lambda _: self._on_change())
        self._window_dd.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        # --- Cooldown ---
        cd_frame = ttk.Frame(self, style="Card.TFrame")
        cd_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=4, pady=(2, 6))
        ttk.Label(cd_frame, text="Cooldown:", style="Card.Small.TLabel").pack(side=tk.LEFT)
        self._cooldown_var = tk.StringVar(value="0.0")
        ttk.Entry(cd_frame, textvariable=self._cooldown_var, width=6).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(cd_frame, text="s", style="Card.Muted.TLabel").pack(side=tk.LEFT)
        self._cooldown_var.trace_add("write", lambda *_: self._on_change())

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=6, column=0, columnspan=3, sticky="ew", padx=4
        )

    def _show_cond_extra(self):
        if self._cond_var is None:
            return
        cond_idx = ["immediate", "wait_time", "wait_primary", "wait_trigger"].index(
            self._cond_var.get()
        ) if self._cond_var.get() in ["immediate","wait_time","wait_primary","wait_trigger"] else 0
        if cond_idx == 1:
            self._wait_secs_entry.pack(side=tk.LEFT)
        else:
            self._wait_secs_entry.pack_forget()

    def update_link_options(self, options: list[tuple]) -> None:
        """Update the link-target combobox with [(id, name), ...]."""
        if self._trigger_src_var is None:
            return
        names = [n for _, n in options]
        self._link_combo["values"] = names
        self._link_options = options

    def set_index(self, idx: int) -> None:
        self._index = idx

    # ------------------------------------------------------------------
    # State extraction

    def get_state(self) -> dict:
        state: dict = {
            "id":     self._id,
            "name":   self._name_var.get(),
            "action": self._binding_box.get_binding(),
            "target_hwnd": self._window_dd.get_hwnd(),
            "cooldown": self._safe_float(self._cooldown_var.get(), 0.0),
        }
        if self._adv_mode == "parallel" and self._trigger_src_var:
            src = self._trigger_src_var.get()
            if src == "own":
                state["trigger_source"] = "own"
            else:
                cur = self._link_combo.current()
                if hasattr(self, "_link_options") and 0 <= cur < len(self._link_options):
                    state["trigger_source"] = f"link:{self._link_options[cur][0]}"
                else:
                    state["trigger_source"] = "own"
        if self._adv_mode == "sequence" and self._cond_var:
            cond_map = {
                "Nothing (immediate)":      "immediate",
                "Time":                     "wait_time",
                "Primary trigger again":    "wait_primary",
                "New trigger image":        "wait_trigger",
            }
            raw = self._cond_combo.get() if hasattr(self, "_cond_combo") else "immediate"
            cond_type = cond_map.get(raw, "immediate")
            state["pre_condition"] = {
                "type": cond_type,
                "wait_seconds": self._safe_float(
                    self._wait_secs_var.get() if hasattr(self, "_wait_secs_var") else "1.0",
                    1.0
                ),
            }
        return state

    @staticmethod
    def _safe_float(s: str, default: float) -> float:
        try:
            return max(0.0, float(s))
        except (ValueError, TypeError):
            return default


# ===========================================================================
# TargetList
# ===========================================================================

class TargetList(ttk.Frame):
    """
    Scrollable list of TargetItem widgets.  Exposes add/remove/reorder.
    """

    def __init__(
        self,
        parent,
        adv_mode: str = "sequence",
        on_change: Optional[Callable] = None,
        theme_manager=None,
        hotkey_manager=None,
        **kw,
    ):
        super().__init__(parent, **kw)
        self._adv_mode   = adv_mode
        self._on_change  = on_change
        self._tm         = theme_manager
        self._hm         = hotkey_manager
        self._items: list[TargetItem] = []
        self._next_id    = 1

        self._build()

    def _build(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Scrollable canvas
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._canvas.config(yscrollcommand=scroll.set)

        self._inner = ttk.Frame(self._canvas)
        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"
        ))

        # Add button
        add_frame = ttk.Frame(self)
        add_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(add_frame, text="+ Add Target", command=self.add_target).pack()

        # Seed with one target
        self.add_target()

    def _on_inner_configure(self, _event=None):
        self._canvas.config(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._window_id, width=event.width)

    # ------------------------------------------------------------------

    def add_target(self) -> None:
        tid = f"t{self._next_id}"
        self._next_id += 1

        item = TargetItem(
            self._inner,
            target_id=tid,
            index=len(self._items),
            adv_mode=self._adv_mode,
            other_targets=self._peer_targets_for(tid),
            on_move_up=lambda tid=tid: self._move(tid, -1),
            on_move_down=lambda tid=tid: self._move(tid, +1),
            on_delete=self._delete,
            on_change=self._changed,
            theme_manager=self._tm,
            hotkey_manager=self._hm,
        )
        item.pack(fill=tk.X, padx=4, pady=3)
        self._items.append(item)
        self._refresh_indices()
        self._changed()

    def _delete(self, tid: str) -> None:
        if len(self._items) <= 1:
            return  # keep at least one
        for item in self._items:
            if item._id == tid:
                item.pack_forget()
                item.destroy()
                self._items.remove(item)
                break
        self._refresh_indices()
        self._changed()

    def _move(self, tid: str, direction: int) -> None:
        idx = next((i for i, it in enumerate(self._items) if it._id == tid), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._items):
            return
        self._items[idx], self._items[new_idx] = self._items[new_idx], self._items[idx]
        self._repack()
        self._refresh_indices()
        self._changed()

    def _repack(self) -> None:
        for item in self._items:
            item.pack_forget()
        for item in self._items:
            item.pack(fill=tk.X, padx=4, pady=3)

    def _refresh_indices(self) -> None:
        for i, item in enumerate(self._items):
            item.set_index(i)
        # Update link options for parallel mode
        if self._adv_mode == "parallel":
            for item in self._items:
                peers = self._peer_targets_for(item._id)
                item.update_link_options(peers)

    def _peer_targets_for(self, tid: str) -> list[tuple]:
        return [(it._id, it._name_var.get())
                for it in self._items if it._id != tid]

    def _changed(self) -> None:
        if self._on_change:
            self._on_change()

    def get_states(self) -> list[dict]:
        return [item.get_state() for item in self._items]

    def set_mode(self, mode: str) -> None:
        """Rebuild items when switching between sequence/parallel."""
        self._adv_mode = mode
        # Preserve names and actions only
        saved = [(it._name_var.get(), it._binding_box.get_binding()) for it in self._items]
        for item in self._items:
            item.pack_forget()
            item.destroy()
        self._items.clear()
        for _ in saved:
            self.add_target()
        self._changed()
