"""
Main application window for Noc Clicker.

Layout
------
  Menu bar  (File | View | Help)
  Mode tabs (Simple | Advanced)
  ├─ Simple panel
  └─ Advanced panel
  Hotkeys panel   (always visible)
  Log / status    (always visible)
  Footer          ("created by noctuem_")

Simple mode
-----------
  Trigger: image region OR keystroke (toggle / hold)
  Action:  click or key press
  Target window, interval, cooldown, poll interval, threshold
  Start / Stop button

Advanced mode
-------------
  Primary trigger region
  Mode: Sequence | Parallel   +  Sequential | Random (sequence only)
  Target list (TargetList widget)
  Start / Stop button
"""

from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

import mss
from PIL import Image, ImageTk

import actions
import engine as eng
import profile as prof
from assets import FONT_FAMILY
import hotkey as hk
from region_selector import RegionSelector, PointSelector
from theme import ThemeManager
from widgets import (
    BindingBox, ColorSwatch, ColorPickerDialog,
    RegionPreview, TargetList, WindowDropdown,
)

PAD  = {"padx": 8, "pady": 4}
PAD2 = {"padx": 4, "pady": 2}
THUMB = (148, 100)


# ---------------------------------------------------------------------------
# Utility: recursively enable/disable all widgets in a container
# ---------------------------------------------------------------------------

def _set_children_state(widget, state: str) -> None:
    """Recursively set the state of a widget and all its descendants."""
    try:
        widget.config(state=state)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        _set_children_state(child, state)


# ===========================================================================
# Theme editor dialog
# ===========================================================================

class ThemeEditorDialog(tk.Toplevel):
    """Lets the user customise every colour key in the current palette."""

    def __init__(self, parent, tm: ThemeManager):
        super().__init__(parent)
        self.title("Theme Editor")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._tm = tm
        self._swatches: dict[str, ColorSwatch] = {}
        self._build()
        self.wait_window()

    def _build(self):
        f = FONT_FAMILY
        ttk.Label(self, text="Colour Keys", style="Header.TLabel").pack(**PAD)

        canvas = tk.Canvas(self, highlightthickness=0, bd=0, width=360, height=420)
        canvas.pack(fill=tk.BOTH, expand=True, padx=8)
        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.config(yscrollcommand=scroll.set)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))

        for row, (key, val) in enumerate(self._tm.PALETTE.items()):
            ttk.Label(inner, text=key, style="Small.TLabel", width=22,
                      anchor="w").grid(row=row, column=0, padx=4, pady=2, sticky="w")
            sw = ColorSwatch(inner, color=val,
                             on_change=lambda c, k=key: self._apply(k, c))
            sw.grid(row=row, column=1, padx=4, pady=2)
            self._swatches[key] = sw

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=8)
        ttk.Button(btn_frame, text="Save as Custom",
                   style="Accent.TButton", command=self._save).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Reset to Dark",
                   command=lambda: self._reset("dark")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Reset to Light",
                   command=lambda: self._reset("light")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Close",
                   command=self.destroy).pack(side=tk.LEFT, padx=4)

    def _apply(self, key: str, color: str) -> None:
        self._tm.set_custom_color(key, color)

    def _save(self) -> None:
        self._tm.apply("custom")
        messagebox.showinfo("Theme saved", "Custom theme applied and saved.", parent=self)

    def _reset(self, name: str) -> None:
        self._tm.apply(name)
        self.destroy()


# ===========================================================================
# Simple mode panel
# ===========================================================================

class SimplePanel(ttk.Frame):
    def __init__(self, parent, app: "App", **kw):
        super().__init__(parent, **kw)
        self._app = app
        self._region_abs:  Optional[dict]          = None
        self._region_rel:  Optional[dict]          = None
        self._monitors:    Optional[list]          = None
        self._trigger_img: Optional[Image.Image]   = None
        self._click_target: Optional[tuple]        = None   # (x, y) abs coords
        self._build()

    def _build(self):
        f = FONT_FAMILY
        app = self._app

        # --- Trigger section ---
        trig_frame = ttk.LabelFrame(self, text="Trigger")
        trig_frame.pack(fill=tk.X, **PAD)

        self._trig_type = tk.StringVar(value="keystroke")
        type_row = ttk.Frame(trig_frame)
        type_row.pack(fill=tk.X, **PAD2)
        ttk.Radiobutton(type_row, text="Image Region",
                        variable=self._trig_type, value="image",
                        command=self._trig_type_changed).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(type_row, text="Keystroke",
                        variable=self._trig_type, value="keystroke",
                        command=self._trig_type_changed).pack(side=tk.LEFT)

        # Image sub-panel
        self._img_panel = ttk.Frame(trig_frame)
        self._img_panel.pack(fill=tk.X, **PAD2)
        ttk.Button(self._img_panel, text="Select Region & Capture",
                   command=self._select_region).pack(side=tk.LEFT, padx=(0, 8))
        self._region_preview = RegionPreview(self._img_panel)
        self._region_preview.pack(side=tk.LEFT)

        self._thresh_row = ttk.Frame(trig_frame)
        thresh_row = self._thresh_row
        thresh_row.pack(fill=tk.X, **PAD2)
        ttk.Label(thresh_row, text="Similarity:").pack(side=tk.LEFT)
        self._threshold_var = tk.IntVar(value=90)
        self._thresh_slider = ttk.Scale(thresh_row, from_=50, to=100,
                                         variable=self._threshold_var, orient=tk.HORIZONTAL)
        self._thresh_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self._thresh_lbl = ttk.Label(thresh_row, text="90%", width=5)
        self._thresh_lbl.pack(side=tk.LEFT, padx=(4, 0))
        self._threshold_var.trace_add("write", lambda *_: self._thresh_lbl.config(
            text=f"{self._threshold_var.get()}%"
        ))

        # Keystroke sub-panel
        self._ks_panel = ttk.Frame(trig_frame)
        ks_row = ttk.Frame(self._ks_panel)
        ks_row.pack(fill=tk.X, **PAD2)
        ttk.Label(ks_row, text="Key:").pack(side=tk.LEFT)
        self._ks_binding_box = BindingBox(ks_row, allow_mouse=False,
                                           on_change=lambda _: self._update_start_state(),
                                           theme_manager=app.theme,
                                           hotkey_manager=app._hotkeys)
        self._ks_binding_box.pack(side=tk.LEFT, padx=(4, 12), fill=tk.X, expand=True)

        self._ks_mode_var = tk.StringVar(value="toggle")
        ttk.Radiobutton(ks_row, text="Toggle", variable=self._ks_mode_var,
                        value="toggle").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(ks_row, text="Hold", variable=self._ks_mode_var,
                        value="hold").pack(side=tk.LEFT)

        # --- Action section ---
        act_frame = ttk.LabelFrame(self, text="Action")
        act_frame.pack(fill=tk.X, **PAD)

        act_row = ttk.Frame(act_frame)
        act_row.pack(fill=tk.X, **PAD2)
        ttk.Label(act_row, text="Action:").pack(side=tk.LEFT)
        self._action_box = BindingBox(act_row, allow_mouse=True,
                                      theme_manager=app.theme,
                                      hotkey_manager=app._hotkeys)
        self._action_box.set_binding(actions.make_binding("click", button="left"))
        self._action_box.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        # Click target row — only shown in image trigger mode
        self._click_target_row = ttk.Frame(act_frame)
        ttk.Label(self._click_target_row, text="Click target:").pack(side=tk.LEFT)
        self._click_target_btn = ttk.Button(
            self._click_target_row, text="Set target",
            command=self._pick_click_target,
        )
        self._click_target_btn.pack(side=tk.LEFT, padx=(4, 8))
        self._click_target_lbl = ttk.Label(
            self._click_target_row, text="— use cursor position",
            style="Muted.TLabel",
        )
        self._click_target_lbl.pack(side=tk.LEFT)

        win_row = ttk.Frame(act_frame)
        win_row.pack(fill=tk.X, **PAD2)
        ttk.Label(win_row, text="Window:").pack(side=tk.LEFT)
        self._window_dd = WindowDropdown(win_row)
        self._window_dd.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        # --- Timing section ---
        self._timing_frame = ttk.LabelFrame(self, text="Timing")
        self._timing_frame.pack(fill=tk.X, **PAD)

        def _timing_row(parent, label, tooltip, var, unit="s"):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, **PAD2)
            ttk.Label(row, text=label, width=16, anchor="w").pack(side=tk.LEFT)
            ent = ttk.Entry(row, textvariable=var, width=7)
            ent.pack(side=tk.LEFT)
            ttk.Label(row, text=unit, style="Muted.TLabel").pack(side=tk.LEFT, padx=(2, 4))
            ttk.Label(row, text=tooltip, style="Muted.TLabel").pack(side=tk.LEFT)
            return row

        self._interval_var = tk.StringVar(value="1.0")
        self._cooldown_var = tk.StringVar(value="1.0")
        self._poll_var     = tk.StringVar(value="0.1")

        # Keystroke-only row
        self._row_interval = _timing_row(
            self._timing_frame, "Fire interval:", "time between each action",
            self._interval_var,
        )
        # Image-only rows
        self._row_cooldown = _timing_row(
            self._timing_frame, "Refire delay:", "wait after trigger fires before re-arming",
            self._cooldown_var,
        )
        self._row_poll = _timing_row(
            self._timing_frame, "Scan rate:", "how often the screen is checked",
            self._poll_var,
        )

        # --- Start / Stop ---
        self._start_btn = ttk.Button(self, text="Start",
                                      style="Accent.TButton",
                                      command=app.toggle_start_stop,
                                      state=tk.DISABLED)
        self._start_btn.pack(fill=tk.X, **PAD)

        # Now safe to call — _start_btn exists
        self._trig_type_changed()

    # ------------------------------------------------------------------

    def _trig_type_changed(self):
        t = self._trig_type.get()
        if t == "image":
            self._img_panel.pack(fill=tk.X, **PAD2)
            self._thresh_row.pack(fill=tk.X, **PAD2)
            self._ks_panel.pack_forget()
            self._row_interval.pack_forget()
            self._row_cooldown.pack(fill=tk.X, **PAD2)
            self._row_poll.pack(fill=tk.X, **PAD2)
            self._click_target_row.pack(fill=tk.X, **PAD2)
        else:
            self._img_panel.pack_forget()
            self._thresh_row.pack_forget()
            self._ks_panel.pack(fill=tk.X, **PAD2)
            self._row_cooldown.pack_forget()
            self._row_poll.pack_forget()
            self._row_interval.pack(fill=tk.X, **PAD2)
            self._click_target_row.pack_forget()
        self._update_start_state()

    def _select_region(self):
        self._app.root.withdraw()
        self._app.root.after(200, self._open_selector)

    def _open_selector(self):
        RegionSelector(on_select=self._on_region_selected)

    def _on_region_selected(self, abs_r, rel_r, monitors):
        self._app.root.deiconify()
        if abs_r is None:
            return
        self._region_abs  = abs_r
        self._region_rel  = rel_r
        self._monitors    = monitors
        with mss.mss() as sct:
            shot = sct.grab(abs_r)
            self._trigger_img = Image.frombytes("RGB", shot.size, shot.rgb)
        self._region_preview.set_image(self._trigger_img)
        self._update_start_state()

    def _pick_click_target(self):
        self._app.root.withdraw()
        self._app.root.after(200, lambda: PointSelector(on_select=self._on_click_target_selected))

    def _on_click_target_selected(self, x, y):
        self._app.root.deiconify()
        if x is None:
            return
        self._click_target = (x, y)
        self._click_target_lbl.config(text=f"x={x},  y={y}")

    def _update_start_state(self):
        t = self._trig_type.get()
        if t == "image":
            ok = self._trigger_img is not None
        else:
            ok = self._ks_binding_box.get_binding() is not None
        state = tk.NORMAL if ok else tk.DISABLED
        if hasattr(self, "_start_btn"):
            self._start_btn.config(state=state)

    def set_running(self, running: bool) -> None:
        self._start_btn.config(text="Stop" if running else "Start")
        state = tk.DISABLED if running else tk.NORMAL
        # Lock everything except the Start/Stop button itself
        for section in (self._img_panel, self._thresh_row, self._ks_panel,
                        self._timing_frame, self._click_target_row):
            _set_children_state(section, state)

    def build_engine_config(self) -> dict:
        t = self._trig_type.get()
        cfg = {
            "trigger_type":  t,
            "action":        self._action_box.get_binding(),
            "target_hwnd":   self._window_dd.get_hwnd(),
            "interval":      _safe_float(self._interval_var.get(), 1.0),
            "cooldown":      _safe_float(self._cooldown_var.get(), 1.0),
            "poll_interval": _safe_float(self._poll_var.get(), 0.1),
            "threshold":     self._threshold_var.get() / 100.0,
        }
        if t == "image":
            cfg["region"]      = self._region_abs
            cfg["trigger_img"] = self._trigger_img
            cfg["click_pos"]   = self._click_target   # None = use current cursor
        else:
            cfg["keystroke_binding"] = self._ks_binding_box.get_binding()
            cfg["keystroke_mode"]    = self._ks_mode_var.get()
        return cfg

    def get_state(self) -> dict:
        return {
            "trigger_type":       self._trig_type.get(),
            "region_rel":         self._region_rel,
            "monitors":           None,   # not serialised
            "trigger_img":        self._trigger_img,
            "threshold":          self._threshold_var.get(),
            "action":             self._action_box.get_binding(),
            "target_hwnd":        self._window_dd.get_hwnd(),
            "interval":           self._interval_var.get(),
            "cooldown":           self._cooldown_var.get(),
            "poll_interval":      self._poll_var.get(),
            "keystroke_binding":  self._ks_binding_box.get_binding(),
            "keystroke_mode":     self._ks_mode_var.get(),
            "click_target":       list(self._click_target) if self._click_target else None,
        }

    def load_state(self, s: dict) -> None:
        self._trig_type.set(s.get("trigger_type", "keystroke"))
        self._threshold_var.set(s.get("threshold", 90))
        self._interval_var.set(s.get("interval", "1.0"))
        self._cooldown_var.set(s.get("cooldown", "1.0"))
        self._poll_var.set(s.get("poll_interval", "0.1"))
        self._action_box.set_binding(s.get("action"))
        self._window_dd.set_hwnd(s.get("target_hwnd"))
        self._ks_binding_box.set_binding(s.get("keystroke_binding"))
        self._ks_mode_var.set(s.get("keystroke_mode", "toggle"))

        rel = s.get("region_rel")
        img = s.get("trigger_img")
        if rel:
            self._region_rel = rel
            self._region_abs = prof.region_to_absolute(rel)
        if img:
            self._trigger_img = img
            self._region_preview.set_image(img)
        ct = s.get("click_target")
        if ct:
            self._click_target = tuple(ct)
            self._click_target_lbl.config(text=f"x={ct[0]},  y={ct[1]}")
        self._trig_type_changed()
        self._update_start_state()


# ===========================================================================
# Advanced mode panel
# ===========================================================================

class AdvancedPanel(ttk.Frame):
    def __init__(self, parent, app: "App", **kw):
        super().__init__(parent, **kw)
        self._app         = app
        self._region_abs: Optional[dict] = None
        self._region_rel: Optional[dict] = None
        self._monitors:   Optional[list] = None
        self._trigger_img: Optional[Image.Image] = None
        self._build()

    def _build(self):
        f   = FONT_FAMILY
        app = self._app

        # --- Primary trigger ---
        self._pt_frame = ttk.LabelFrame(self, text="Primary Trigger")
        pt_frame = self._pt_frame
        pt_frame.pack(fill=tk.X, **PAD)

        pt_row = ttk.Frame(pt_frame)
        pt_row.pack(fill=tk.X, **PAD2)
        ttk.Button(pt_row, text="Select Region",
                   command=self._select_region).pack(side=tk.LEFT, padx=(0, 8))
        self._pt_preview = RegionPreview(pt_row)
        self._pt_preview.pack(side=tk.LEFT)

        thresh_row = ttk.Frame(pt_frame)
        thresh_row.pack(fill=tk.X, **PAD2)
        ttk.Label(thresh_row, text="Similarity:").pack(side=tk.LEFT)
        self._threshold_var = tk.IntVar(value=90)
        ttk.Scale(thresh_row, from_=50, to=100,
                  variable=self._threshold_var, orient=tk.HORIZONTAL
                  ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self._thresh_lbl = ttk.Label(thresh_row, text="90%", width=5)
        self._thresh_lbl.pack(side=tk.LEFT, padx=(4, 0))
        self._threshold_var.trace_add("write", lambda *_: self._thresh_lbl.config(
            text=f"{self._threshold_var.get()}%"
        ))

        poll_row = ttk.Frame(pt_frame)
        poll_row.pack(fill=tk.X, **PAD2)
        ttk.Label(poll_row, text="Poll interval:", width=14, anchor="w").pack(side=tk.LEFT)
        self._poll_var = tk.StringVar(value="0.1")
        ttk.Entry(poll_row, textvariable=self._poll_var, width=7).pack(side=tk.LEFT)
        ttk.Label(poll_row, text="s", style="Muted.TLabel").pack(side=tk.LEFT, padx=(2, 0))

        # --- Mode ---
        self._mode_frame = ttk.LabelFrame(self, text="Mode")
        mode_frame = self._mode_frame
        mode_frame.pack(fill=tk.X, **PAD)

        mode_row = ttk.Frame(mode_frame)
        mode_row.pack(fill=tk.X, **PAD2)
        self._adv_mode_var = tk.StringVar(value="sequence")
        ttk.Radiobutton(mode_row, text="Sequence",
                        variable=self._adv_mode_var, value="sequence",
                        command=self._mode_changed).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(mode_row, text="Parallel",
                        variable=self._adv_mode_var, value="parallel",
                        command=self._mode_changed).pack(side=tk.LEFT)

        self._order_frame = ttk.Frame(mode_frame)
        self._order_frame.pack(fill=tk.X, **PAD2)
        self._order_var = tk.StringVar(value="sequential")
        ttk.Radiobutton(self._order_frame, text="Sequential",
                        variable=self._order_var, value="sequential").pack(side=tk.LEFT, padx=(0,12))
        self._rand_rb = ttk.Radiobutton(self._order_frame,
                        text="Random (all fire once in shuffled order)",
                        variable=self._order_var, value="random")
        self._rand_rb.pack(side=tk.LEFT)

        # --- Target list ---
        list_frame = ttk.LabelFrame(self, text="Targets")
        list_frame.pack(fill=tk.BOTH, expand=True, **PAD)

        self._target_list = TargetList(
            list_frame,
            adv_mode="sequence",
            on_change=self._on_targets_changed,
            theme_manager=app.theme,
            hotkey_manager=app._hotkeys,
        )
        self._target_list.pack(fill=tk.BOTH, expand=True)

        # --- Start / Stop ---
        self._start_btn = ttk.Button(self, text="Start",
                                      style="Accent.TButton",
                                      command=app.toggle_start_stop,
                                      state=tk.DISABLED)
        self._start_btn.pack(fill=tk.X, **PAD)
        self._update_start_state()

    # ------------------------------------------------------------------

    def _select_region(self):
        self._app.root.withdraw()
        self._app.root.after(200, self._open_selector)

    def _open_selector(self):
        RegionSelector(on_select=self._on_region_selected)

    def _on_region_selected(self, abs_r, rel_r, monitors):
        self._app.root.deiconify()
        if abs_r is None:
            return
        self._region_abs = abs_r
        self._region_rel = rel_r
        self._monitors   = monitors
        with mss.mss() as sct:
            shot = sct.grab(abs_r)
            self._trigger_img = Image.frombytes("RGB", shot.size, shot.rgb)
        self._pt_preview.set_image(self._trigger_img)
        self._update_start_state()

    def _mode_changed(self):
        mode = self._adv_mode_var.get()
        if mode == "sequence":
            self._order_frame.pack(fill=tk.X, **PAD2)
        else:
            self._order_frame.pack_forget()
        self._target_list.set_mode(mode)

    def _on_targets_changed(self):
        self._update_start_state()

    def _update_start_state(self):
        ok = self._trigger_img is not None
        if hasattr(self, "_start_btn"):
            self._start_btn.config(state=tk.NORMAL if ok else tk.DISABLED)

    def set_running(self, running: bool) -> None:
        self._start_btn.config(text="Stop" if running else "Start")
        state = tk.DISABLED if running else tk.NORMAL
        for section in (self._pt_frame, self._mode_frame, self._target_list):
            _set_children_state(section, state)

    def build_engine_config(self) -> dict:
        mode    = self._adv_mode_var.get()
        targets = self._target_list.get_states()

        cfg: dict = {
            "adv_mode":       mode,
            "primary_region": self._region_abs,
            "primary_img":    self._trigger_img,
            "threshold":      self._threshold_var.get() / 100.0,
            "poll_interval":  _safe_float(self._poll_var.get(), 0.1),
            "random_order":   self._order_var.get() == "random",
            "targets":        targets,
        }
        return cfg

    def get_state(self) -> dict:
        return {
            "adv_mode":     self._adv_mode_var.get(),
            "order":        self._order_var.get(),
            "region_rel":   self._region_rel,
            "trigger_img":  self._trigger_img,
            "threshold":    self._threshold_var.get(),
            "poll_interval": self._poll_var.get(),
            "targets":      self._target_list.get_states(),
        }

    def load_state(self, s: dict) -> None:
        self._adv_mode_var.set(s.get("adv_mode", "sequence"))
        self._order_var.set(s.get("order", "sequential"))
        self._threshold_var.set(s.get("threshold", 90))
        self._poll_var.set(s.get("poll_interval", "0.1"))

        rel = s.get("region_rel")
        img = s.get("trigger_img")
        if rel:
            self._region_rel = rel
            self._region_abs = prof.region_to_absolute(rel)
        if img:
            self._trigger_img = img
            self._pt_preview.set_image(img)

        self._mode_changed()
        self._update_start_state()


# ===========================================================================
# Hotkeys panel
# ===========================================================================

class HotkeysPanel(ttk.LabelFrame):
    def __init__(self, parent, app: "App", **kw):
        super().__init__(parent, text="Global Hotkeys", **kw)
        self._app = app
        self._build()

    def _build(self):
        row1 = ttk.Frame(self)
        row1.pack(fill=tk.X, **PAD2)
        ttk.Label(row1, text="Start / Stop:", width=12, anchor="w").pack(side=tk.LEFT)
        self._start_box = BindingBox(row1, allow_mouse=False,
                                      on_change=self._on_start_change,
                                      theme_manager=self._app.theme,
                                      hotkey_manager=self._app._hotkeys)
        self._start_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    def _on_start_change(self, b: dict) -> None:
        self._app.update_start_stop_hotkey(b)

    def get_state(self) -> dict:
        return {"start_stop": self._start_box.get_binding()}

    def load_state(self, s: dict) -> None:
        self._start_box.set_binding(s.get("start_stop"))
        self._app.update_start_stop_hotkey(s.get("start_stop"))


# ===========================================================================
# Log widget
# ===========================================================================

class LogPanel(ttk.Frame):
    MAX = 200

    def __init__(self, parent, tm: ThemeManager, **kw):
        super().__init__(parent, **kw)
        self._tm = tm
        self._build()
        tm.on_change(lambda _: self._restyle())

    def _build(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        p = self._tm.PALETTE
        self._text = tk.Text(
            self, height=6, state=tk.DISABLED, wrap=tk.WORD,
            bg=p["log_bg"], fg=p["log_fg"],
            font=(FONT_FAMILY, 9),
            relief="flat", bd=0, insertbackground=p["log_fg"],
        )
        self._text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._text.config(yscrollcommand=scroll.set)

    def _restyle(self):
        p = self._tm.PALETTE
        self._text.config(bg=p["log_bg"], fg=p["log_fg"])

    def append(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._text.config(state=tk.NORMAL)
        self._text.insert(tk.END, line)
        # Trim to MAX lines
        lines = int(self._text.index(tk.END).split(".")[0]) - 1
        if lines > self.MAX:
            self._text.delete("1.0", f"{lines - self.MAX}.0")
        self._text.see(tk.END)
        self._text.config(state=tk.DISABLED)


# ===========================================================================
# Main App
# ===========================================================================

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Noc Clicker")
        self.root.resizable(True, True)

        self.theme   = ThemeManager(root)
        self._engine = eng.Engine(
            on_status=self._on_status,
            on_log=self._on_log,
        )
        self._hotkeys        = hk.HotkeyManager()
        self._ks_capture:    Optional[hk.BindingCapture] = None
        self._ks_running     = False   # for keystroke-trigger simple mode
        self._ks_binding:    Optional[dict] = None
        self._ks_mode:       str = "toggle"

        self._start_stop_binding: Optional[dict] = None
        self._app_running: bool = False   # true whenever automation is active

        self._hotkeys.start()
        self._build_ui()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.theme.on_change(lambda _: self._retheme())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        f   = FONT_FAMILY
        p   = self.theme.PALETTE

        self._build_menu()

        # Notebook for Simple / Advanced
        self._notebook = ttk.Notebook(self.root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 0))

        self._simple_scroll_frame   = _ScrollableFrame(self._notebook)
        self._advanced_scroll_frame = _ScrollableFrame(self._notebook)

        self._simple_panel   = SimplePanel(self._simple_scroll_frame.inner, app=self)
        self._advanced_panel = AdvancedPanel(self._advanced_scroll_frame.inner, app=self)
        self._simple_panel.pack(fill=tk.BOTH, expand=True)
        self._advanced_panel.pack(fill=tk.BOTH, expand=True)

        self._notebook.add(self._simple_scroll_frame,   text="  Simple  ")
        self._notebook.add(self._advanced_scroll_frame, text="  Advanced  ")

        # Hotkeys panel
        self._hotkeys_panel = HotkeysPanel(self.root, app=self)
        self._hotkeys_panel.pack(fill=tk.X, padx=6, pady=(4, 0))

        # Status label
        self._status_var = tk.StringVar(value="Idle")
        ttk.Label(self.root, textvariable=self._status_var,
                  style="Muted.TLabel").pack(padx=6, pady=(2, 0), anchor="w")

        # Log
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill=tk.X, padx=6, pady=(2, 0))
        self._log_panel = LogPanel(log_frame, tm=self.theme)
        self._log_panel.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Footer
        footer = ttk.Frame(self.root)
        footer.pack(fill=tk.X, padx=6, pady=(2, 4))
        ttk.Label(footer, text="created by noctuem_",
                  style="Muted.TLabel", font=(f, 7)).pack(side=tk.RIGHT)

        self.root.minsize(460, 580)
        self.root.geometry("480x780")

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Profile",    command=self._profile_new)
        file_menu.add_command(label="Save Profile",   command=self._profile_save)
        file_menu.add_command(label="Load Profile…",  command=self._profile_load)
        file_menu.add_separator()
        file_menu.add_command(label="Delete Profile…",command=self._profile_delete)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",            command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # View
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Dark Theme",    command=lambda: self.theme.apply("dark"))
        view_menu.add_command(label="Light Theme",   command=lambda: self.theme.apply("light"))
        view_menu.add_command(label="Custom Theme",  command=lambda: self.theme.apply("custom"))
        view_menu.add_separator()
        view_menu.add_command(label="Edit Theme…",   command=self._open_theme_editor)
        menubar.add_cascade(label="View", menu=view_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _retheme(self):
        """Called when theme changes; re-colour native tk widgets."""
        p = self.theme.PALETTE
        f = FONT_FAMILY
        try:
            self.root.configure(bg=p["bg_primary"])
        except Exception:
            pass

    def _open_theme_editor(self):
        ThemeEditorDialog(self.root, self.theme)

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------

    def update_start_stop_hotkey(self, b: Optional[dict]) -> None:
        if self._start_stop_binding:
            self._hotkeys.unregister(
                self._start_stop_binding.get("mods", []),
                self._start_stop_binding.get("vk", 0),
            )
        self._start_stop_binding = b
        if b and b.get("type") == "key" and b.get("vk"):
            self._hotkeys.register(
                b.get("mods", []), b["vk"],
                callback=lambda: self.root.after(0, self.toggle_start_stop),
                name="start_stop",
            )

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def toggle_start_stop(self) -> None:
        if self._app_running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        tab = self._notebook.index(self._notebook.select())
        if tab == 0:
            cfg = self._simple_panel.build_engine_config()
            if cfg.get("trigger_type") == "keystroke":
                self._start_keystroke_mode(cfg)
                return
            self._engine.configure_simple(cfg)
        else:
            cfg = self._advanced_panel.build_engine_config()
            self._engine.configure_advanced(cfg)

        self._engine.start()
        self._set_running(True)

    def _stop(self) -> None:
        self._engine.stop()
        self._cleanup_keystroke_mode()
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self._app_running = running
        self._simple_panel.set_running(running)
        self._advanced_panel.set_running(running)

    # ------------------------------------------------------------------
    # Keystroke trigger mode
    # ------------------------------------------------------------------

    def _start_keystroke_mode(self, cfg: dict) -> None:
        binding = cfg.get("keystroke_binding")
        mode    = cfg.get("keystroke_mode", "toggle")
        if not binding or not binding.get("vk"):
            return

        self._ks_binding = binding
        self._ks_mode    = mode
        self._ks_running = False

        action    = cfg.get("action")
        hwnd      = cfg.get("target_hwnd")
        interval  = cfg.get("interval", 1.0)

        fire_cfg = {
            "trigger_type": "keystroke",
            "action": action,
            "target_hwnd": hwnd,
            "interval": interval,
            "cooldown": 0.0,
        }

        def on_press():
            if mode == "toggle":
                if self._ks_running:
                    self._ks_running = False
                    self._engine.stop()
                    self.root.after(0, lambda: self._on_status("Keystroke trigger armed (paused)"))
                else:
                    self._ks_running = True
                    self._engine.configure_simple(fire_cfg)
                    self._engine.start()
            else:  # hold — start on press
                if not self._ks_running:
                    self._ks_running = True
                    self._engine.configure_simple(fire_cfg)
                    self._engine.start()

        def on_release():
            if mode == "hold" and self._ks_running:
                self._ks_running = False
                self._engine.stop()
                self.root.after(0, lambda: self._on_status("Keystroke trigger armed"))

        self._hotkeys.register(
            binding.get("mods", []), binding["vk"],
            callback=on_press,
            name="ks_trigger",
        )
        if mode == "hold":
            self._hotkeys.register_release(binding["vk"], callback=on_release, name="ks_release")

        self._set_running(True)
        self._on_status("Keystroke trigger armed")

    def _cleanup_keystroke_mode(self) -> None:
        if self._ks_binding:
            vk = self._ks_binding.get("vk", 0)
            self._hotkeys.unregister(self._ks_binding.get("mods", []), vk)
            self._hotkeys.unregister_release(vk)
            self._ks_binding = None
        self._ks_running = False

    # ------------------------------------------------------------------
    # Engine callbacks (called from worker threads)
    # ------------------------------------------------------------------

    def _on_status(self, msg: str) -> None:
        self.root.after(0, lambda: self._status_var.set(msg))

    def _on_log(self, msg: str) -> None:
        self.root.after(0, lambda: self._log_panel.append(msg))

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _get_full_state(self) -> dict:
        return {
            "mode":         self._notebook.index(self._notebook.select()),
            "simple":       self._simple_panel.get_state(),
            "advanced":     self._advanced_panel.get_state(),
            "hotkeys":      self._hotkeys_panel.get_state(),
            "theme_active": self.theme.active,
            "theme_custom": self.theme._custom,
        }

    def _load_full_state(self, s: dict) -> None:
        tab = s.get("mode", 0)
        self._notebook.select(tab)

        if "simple" in s:
            self._simple_panel.load_state(s["simple"])
        if "advanced" in s:
            self._advanced_panel.load_state(s["advanced"])
        if "hotkeys" in s:
            self._hotkeys_panel.load_state(s["hotkeys"])

        # Theme
        if "theme_custom" in s:
            from theme import _DARK
            merged = dict(_DARK)
            merged.update(s["theme_custom"])
            self.theme._custom = merged
        active = s.get("theme_active", "dark")
        self.theme.apply(active)

    def _profile_new(self) -> None:
        if self._engine.is_running:
            messagebox.showwarning("Running", "Stop the engine before managing profiles.")
            return
        # Reset to defaults
        self._simple_panel.load_state({})
        self._advanced_panel.load_state({})
        self._on_status("New profile (unsaved)")

    def _profile_save(self) -> None:
        name = simpledialog.askstring(
            "Save Profile", "Profile name:", parent=self.root
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return
        existing = prof.list_profiles()
        if name in existing:
            if not messagebox.askyesno(
                "Overwrite?", f"Profile '{name}' exists. Overwrite?", parent=self.root
            ):
                return
        try:
            state = self._get_full_state()
            prof.save_profile(name, state)
            self._on_log(f"Profile saved: {name}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self.root)

    def _profile_load(self) -> None:
        profiles = prof.list_profiles()
        if not profiles:
            messagebox.showinfo("No profiles", "No saved profiles found.", parent=self.root)
            return
        dlg = _ListPickerDialog(self.root, title="Load Profile",
                                 prompt="Select a profile:", items=profiles)
        name = dlg.result
        if not name:
            return
        state = prof.load_profile(name)
        if state is None:
            messagebox.showerror("Load failed", f"Could not load '{name}'.", parent=self.root)
            return
        try:
            self._load_full_state(state)
            self._on_log(f"Profile loaded: {name}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e), parent=self.root)

    def _profile_delete(self) -> None:
        profiles = prof.list_profiles()
        if not profiles:
            messagebox.showinfo("No profiles", "No saved profiles found.", parent=self.root)
            return
        dlg = _ListPickerDialog(self.root, title="Delete Profile",
                                 prompt="Select a profile to delete:", items=profiles)
        name = dlg.result
        if not name:
            return
        if messagebox.askyesno("Confirm", f"Delete profile '{name}'?", parent=self.root):
            prof.delete_profile(name)
            self._on_log(f"Profile deleted: {name}")

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _about(self) -> None:
        messagebox.showinfo(
            "Noc Clicker",
            "Noc Clicker\n"
            "Image-triggered auto-clicker / key sender\n\n"
            "Created by noctuem_\n"
            "MIT License",
            parent=self.root,
        )

    def _on_close(self) -> None:
        if self._engine.is_running:
            self._engine.abort()
        self._hotkeys.stop()
        self.theme.save()
        self.root.destroy()


# ===========================================================================
# Helper: scrollable frame wrapper
# ===========================================================================

class _ScrollableFrame(ttk.Frame):
    """A frame with a vertical scrollbar; children are added to .inner."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.config(yscrollcommand=scroll.set)

        self.inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=self.inner, anchor="nw")

        def on_configure(_event=None):
            canvas.config(scrollregion=canvas.bbox("all"))

        def on_canvas_resize(event):
            canvas.itemconfig(win, width=event.width)

        self.inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", on_canvas_resize)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"
        ))


# ===========================================================================
# Helper: simple list-picker dialog
# ===========================================================================

class _ListPickerDialog(tk.Toplevel):
    def __init__(self, parent, title: str, prompt: str, items: list[str]):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[str] = None

        ttk.Label(self, text=prompt, style="TLabel").pack(padx=12, pady=(10, 4))

        self._var = tk.StringVar(value=items[0] if items else "")
        lb_frame = ttk.Frame(self)
        lb_frame.pack(padx=12, pady=4)
        scroll = ttk.Scrollbar(lb_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(lb_frame, listvariable=tk.StringVar(value=items),
                        selectmode=tk.SINGLE, height=min(len(items), 10),
                        yscrollcommand=scroll.set, width=36)
        lb.pack(side=tk.LEFT)
        scroll.config(command=lb.yview)
        if items:
            lb.selection_set(0)
        self._lb = lb

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=8)
        ttk.Button(btn_frame, text="OK", style="Accent.TButton",
                   command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel",
                   command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.wait_window()

    def _ok(self) -> None:
        sel = self._lb.curselection()
        if sel:
            self.result = self._lb.get(sel[0])
        self.destroy()


# ===========================================================================
# Utility
# ===========================================================================

def _safe_float(s: str, default: float) -> float:
    try:
        return max(0.0, float(s))
    except (ValueError, TypeError):
        return default
