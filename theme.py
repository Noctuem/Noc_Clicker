"""
Theme system for Noc Clicker.

Stores two built-in palettes (dark / light) plus a user-customisable palette.
Applies colours to the ttk.Style so every widget picks them up automatically.
The active theme name and any custom overrides are persisted to
~/.noctuem/theme.json so they survive across sessions and projects.

Public API
----------
ThemeManager(root)          – create once in main App.__init__
tm.apply(name)              – "dark" | "light" | "custom"
tm.get(key)                 – get a colour string for the current theme
tm.set_custom_color(k, v)   – update one key in the custom palette
tm.save() / tm.load()       – persist to disk
tm.PALETTE                  – dict of current colours
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

from assets import FONT_FAMILY

# ---------------------------------------------------------------------------
# Built-in palettes
# ---------------------------------------------------------------------------

_DARK: dict[str, str] = {
    "bg_primary":    "#0a0a0a",
    "bg_secondary":  "#0f0f0f",
    "bg_tertiary":   "#1a1a1a",
    "bg_hover":      "#242424",
    "accent":        "#cc2b2b",
    "accent_hover":  "#e03c3c",
    "text_primary":  "#e6e6e6",
    "text_secondary":"#999999",
    "text_muted":    "#505050",
    "border":        "#2a2a2a",
    "error":         "#ff5555",
    "success":       "#4caf50",
    "warning":       "#cc7722",
    "button_bg":     "#1a1a1a",
    "button_fg":     "#e6e6e6",
    "entry_bg":      "#0f0f0f",
    "entry_fg":      "#e6e6e6",
    "select_bg":     "#2a1010",
    "select_fg":     "#e6e6e6",
    "scrollbar":     "#242424",
    "log_bg":        "#070707",
    "log_fg":        "#e6e6e6",
    "separator":     "#1a1a1a",
}

_LIGHT: dict[str, str] = {
    "bg_primary":    "#eff1f5",
    "bg_secondary":  "#e6e9ef",
    "bg_tertiary":   "#dce0e8",
    "bg_hover":      "#ccd0da",
    "accent":        "#8839ef",
    "accent_hover":  "#7287fd",
    "text_primary":  "#4c4f69",
    "text_secondary":"#5c5f77",
    "text_muted":    "#9ca0b0",
    "border":        "#bcc0cc",
    "error":         "#d20f39",
    "success":       "#40a02b",
    "warning":       "#fe640b",
    "button_bg":     "#dce0e8",
    "button_fg":     "#4c4f69",
    "entry_bg":      "#ffffff",
    "entry_fg":      "#4c4f69",
    "select_bg":     "#ccd0da",
    "select_fg":     "#4c4f69",
    "scrollbar":     "#bcc0cc",
    "log_bg":        "#dce0e8",
    "log_fg":        "#4c4f69",
    "separator":     "#bcc0cc",
}

BUILTIN: dict[str, dict[str, str]] = {
    "dark":  _DARK,
    "light": _LIGHT,
}

# ---------------------------------------------------------------------------
# Persistence path
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path.home() / ".noctuem"
_THEME_FILE = _CONFIG_DIR / "theme.json"


def _ensure_config_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# ThemeManager
# ---------------------------------------------------------------------------

class ThemeManager:
    def __init__(self, root: "tk.Tk"):
        self._root = root
        self._active: str = "dark"
        self._custom: dict[str, str] = dict(_DARK)  # starts as copy of dark
        self.PALETTE: dict[str, str] = dict(_DARK)
        self._callbacks: list = []

        self.load()
        self._build_style()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def apply(self, name: str) -> None:
        """Switch to 'dark', 'light', or 'custom'."""
        self._active = name
        if name == "custom":
            self.PALETTE = dict(self._custom)
        else:
            self.PALETTE = dict(BUILTIN.get(name, _DARK))
        self._build_style()
        self.save()
        for cb in self._callbacks:
            cb(name)

    def get(self, key: str, fallback: str = "#ffffff") -> str:
        return self.PALETTE.get(key, fallback)

    def set_custom_color(self, key: str, value: str) -> None:
        self._custom[key] = value
        if self._active == "custom":
            self.PALETTE[key] = value
            self._build_style()
            for cb in self._callbacks:
                cb("custom")

    def on_change(self, callback) -> None:
        """Register callback(name) fired whenever the theme changes."""
        self._callbacks.append(callback)

    @property
    def active(self) -> str:
        return self._active

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        _ensure_config_dir()
        data = {
            "active": self._active,
            "custom": self._custom,
        }
        try:
            with open(_THEME_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def load(self) -> None:
        try:
            with open(_THEME_FILE) as f:
                data = json.load(f)
            self._active = data.get("active", "dark")
            loaded_custom = data.get("custom", {})
            # Merge so new keys added in updates get defaults
            merged = dict(_DARK)
            merged.update(loaded_custom)
            self._custom = merged
        except (OSError, json.JSONDecodeError):
            self._active = "dark"
            self._custom = dict(_DARK)

        if self._active == "custom":
            self.PALETTE = dict(self._custom)
        else:
            self.PALETTE = dict(BUILTIN.get(self._active, _DARK))

    # ------------------------------------------------------------------
    # ttk styling
    # ------------------------------------------------------------------

    def _build_style(self) -> None:
        p = self.PALETTE
        f = FONT_FAMILY

        style = ttk.Style(self._root)
        style.theme_use("clam")

        # --- global ---
        style.configure(".",
            background=p["bg_secondary"],
            foreground=p["text_primary"],
            font=(f, 10),
            bordercolor=p["border"],
            darkcolor=p["bg_tertiary"],
            lightcolor=p["bg_tertiary"],
            troughcolor=p["bg_primary"],
            focuscolor=p["accent"],
            selectbackground=p["select_bg"],
            selectforeground=p["select_fg"],
            insertcolor=p["text_primary"],
        )

        # --- TFrame / TLabelframe ---
        for widget in ("TFrame", "TLabelframe"):
            style.configure(widget,
                background=p["bg_secondary"],
                bordercolor=p["border"],
            )
        style.configure("TLabelframe.Label",
            background=p["bg_secondary"],
            foreground=p["text_secondary"],
            font=(f, 9),
        )

        # Card frame (slightly elevated)
        style.configure("Card.TFrame",
            background=p["bg_tertiary"],
            bordercolor=p["border"],
            relief="flat",
        )
        style.configure("Card.TLabelframe",
            background=p["bg_tertiary"],
            bordercolor=p["border"],
        )
        style.configure("Card.TLabelframe.Label",
            background=p["bg_tertiary"],
            foreground=p["text_secondary"],
            font=(f, 9),
        )

        # --- TLabel ---
        style.configure("TLabel",
            background=p["bg_secondary"],
            foreground=p["text_primary"],
            font=(f, 10),
        )
        style.configure("Muted.TLabel",
            background=p["bg_secondary"],
            foreground=p["text_muted"],
            font=(f, 8),
        )
        style.configure("Small.TLabel",
            background=p["bg_secondary"],
            foreground=p["text_secondary"],
            font=(f, 9),
        )
        style.configure("Header.TLabel",
            background=p["bg_secondary"],
            foreground=p["text_primary"],
            font=(f, 11, "bold"),
        )
        style.configure("Error.TLabel",
            background=p["bg_secondary"],
            foreground=p["error"],
            font=(f, 9),
        )
        style.configure("Success.TLabel",
            background=p["bg_secondary"],
            foreground=p["success"],
            font=(f, 9),
        )
        style.configure("Card.TLabel",
            background=p["bg_tertiary"],
            foreground=p["text_primary"],
            font=(f, 10),
        )
        style.configure("Card.Small.TLabel",
            background=p["bg_tertiary"],
            foreground=p["text_secondary"],
            font=(f, 9),
        )
        style.configure("Card.Muted.TLabel",
            background=p["bg_tertiary"],
            foreground=p["text_muted"],
            font=(f, 8),
        )

        # --- TButton ---
        style.configure("TButton",
            background=p["button_bg"],
            foreground=p["button_fg"],
            bordercolor=p["border"],
            focuscolor=p["accent"],
            font=(f, 10),
            padding=(8, 4),
            relief="flat",
        )
        style.map("TButton",
            background=[("active", p["bg_hover"]), ("pressed", p["bg_hover"])],
            foreground=[("disabled", p["text_muted"])],
            bordercolor=[("focus", p["accent"])],
        )

        # Accent button
        style.configure("Accent.TButton",
            background=p["accent"],
            foreground=p["bg_primary"],
            bordercolor=p["accent"],
            font=(f, 10, "bold"),
            padding=(8, 4),
        )
        style.map("Accent.TButton",
            background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])],
            foreground=[("disabled", p["text_muted"])],
        )

        # Danger button
        style.configure("Danger.TButton",
            background=p["error"],
            foreground=p["bg_primary"],
            bordercolor=p["error"],
            font=(f, 10),
            padding=(8, 4),
        )
        style.map("Danger.TButton",
            background=[("active", p["bg_hover"])],
        )

        # Small icon button
        style.configure("Icon.TButton",
            background=p["bg_tertiary"],
            foreground=p["text_secondary"],
            bordercolor=p["bg_tertiary"],
            font=(f, 9),
            padding=(2, 2),
            relief="flat",
        )
        style.map("Icon.TButton",
            background=[("active", p["bg_hover"])],
            foreground=[("active", p["text_primary"])],
        )

        # --- TEntry ---
        style.configure("TEntry",
            fieldbackground=p["entry_bg"],
            foreground=p["entry_fg"],
            bordercolor=p["border"],
            insertcolor=p["text_primary"],
            font=(f, 10),
            padding=(4, 3),
        )
        style.map("TEntry",
            bordercolor=[("focus", p["accent"])],
            fieldbackground=[("readonly", p["bg_tertiary"])],
        )

        # Binding box (special entry-like)
        style.configure("Binding.TEntry",
            fieldbackground=p["bg_tertiary"],
            foreground=p["accent"],
            bordercolor=p["border"],
            insertcolor=p["accent"],
            font=(f, 10),
            padding=(4, 3),
        )
        style.map("Binding.TEntry",
            bordercolor=[("focus", p["accent"])],
            fieldbackground=[("focus", p["bg_primary"])],
        )

        # --- TCombobox ---
        style.configure("TCombobox",
            fieldbackground=p["entry_bg"],
            background=p["button_bg"],
            foreground=p["entry_fg"],
            arrowcolor=p["text_secondary"],
            bordercolor=p["border"],
            font=(f, 10),
            padding=(4, 3),
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", p["bg_tertiary"])],
            bordercolor=[("focus", p["accent"])],
            arrowcolor=[("active", p["accent"])],
        )
        self._root.option_add("*TCombobox*Listbox.background", p["bg_tertiary"])
        self._root.option_add("*TCombobox*Listbox.foreground", p["text_primary"])
        self._root.option_add("*TCombobox*Listbox.selectBackground", p["select_bg"])
        self._root.option_add("*TCombobox*Listbox.selectForeground", p["select_fg"])
        self._root.option_add("*TCombobox*Listbox.font", f"{f} 10")

        # --- TScale ---
        style.configure("TScale",
            background=p["bg_secondary"],
            troughcolor=p["bg_tertiary"],
            sliderrelief="flat",
            sliderlength=14,
        )
        style.map("TScale",
            background=[("active", p["accent"])],
        )

        # --- TScrollbar ---
        style.configure("TScrollbar",
            background=p["scrollbar"],
            troughcolor=p["bg_primary"],
            bordercolor=p["bg_primary"],
            arrowcolor=p["text_muted"],
            relief="flat",
            arrowsize=12,
        )
        style.map("TScrollbar",
            background=[("active", p["text_muted"])],
        )

        # --- TRadiobutton / TCheckbutton ---
        for widget in ("TRadiobutton", "TCheckbutton"):
            style.configure(widget,
                background=p["bg_secondary"],
                foreground=p["text_primary"],
                font=(f, 10),
                indicatorcolor=p["bg_tertiary"],
                indicatormargin=4,
            )
            style.map(widget,
                background=[("active", p["bg_secondary"])],
                foreground=[("disabled", p["text_muted"])],
                indicatorcolor=[
                    ("selected", p["accent"]),
                    ("pressed", p["accent_hover"]),
                ],
            )
        style.configure("Card.TRadiobutton",
            background=p["bg_tertiary"],
        )
        style.map("Card.TRadiobutton",
            background=[("active", p["bg_tertiary"])],
            indicatorcolor=[("selected", p["accent"])],
        )
        style.configure("Card.TCheckbutton",
            background=p["bg_tertiary"],
        )
        style.map("Card.TCheckbutton",
            background=[("active", p["bg_tertiary"])],
            indicatorcolor=[("selected", p["accent"])],
        )

        # --- TNotebook (mode tabs) ---
        style.configure("TNotebook",
            background=p["bg_primary"],
            bordercolor=p["border"],
            tabmargins=(2, 2, 2, 0),
        )
        style.configure("TNotebook.Tab",
            background=p["bg_tertiary"],
            foreground=p["text_muted"],
            font=(f, 10),
            padding=(14, 6),
            bordercolor=p["border"],
        )
        style.map("TNotebook.Tab",
            background=[("selected", p["bg_secondary"]), ("active", p["bg_hover"])],
            foreground=[("selected", p["accent"]), ("active", p["text_primary"])],
            expand=[("selected", (1, 1, 1, 0))],
        )

        # --- TSeparator ---
        style.configure("TSeparator",
            background=p["separator"],
        )

        # --- TPanedwindow ---
        style.configure("TPanedwindow",
            background=p["bg_primary"],
        )

        # Root window background
        self._root.configure(bg=p["bg_primary"])
