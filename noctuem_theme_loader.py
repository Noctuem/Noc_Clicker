"""
noctuem_theme_loader.py
-----------------------
Standalone utility for loading the shared noctuem_ theme from
~/.noctuem/theme.json into any project.

Copy this file into any project that wants to share the noctuem colour palette.

Usage
-----
    from noctuem_theme_loader import NoctuemTheme

    t = NoctuemTheme()
    bg = t.get("bg_primary")      # "#181825"
    palette = t.palette           # full dict
    active = t.active             # "dark" | "light" | "custom"

No external dependencies — stdlib only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Built-in palettes (mirrors theme.py)
# ---------------------------------------------------------------------------

_DARK: dict[str, str] = {
    "bg_primary":    "#181825",
    "bg_secondary":  "#1e1e2e",
    "bg_tertiary":   "#313244",
    "bg_hover":      "#45475a",
    "accent":        "#cba6f7",
    "accent_hover":  "#b4befe",
    "text_primary":  "#cdd6f4",
    "text_secondary":"#a6adc8",
    "text_muted":    "#6c7086",
    "border":        "#45475a",
    "error":         "#f38ba8",
    "success":       "#a6e3a1",
    "warning":       "#fab387",
    "button_bg":     "#313244",
    "button_fg":     "#cdd6f4",
    "entry_bg":      "#1e1e2e",
    "entry_fg":      "#cdd6f4",
    "select_bg":     "#45475a",
    "select_fg":     "#cdd6f4",
    "scrollbar":     "#45475a",
    "log_bg":        "#11111b",
    "log_fg":        "#cdd6f4",
    "separator":     "#313244",
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

_CONFIG_FILE = Path.home() / ".noctuem" / "theme.json"


class NoctuemTheme:
    """Load and expose the shared noctuem_ theme palette."""

    def __init__(self) -> None:
        self._active = "dark"
        self._custom: dict[str, str] = dict(_DARK)
        self._palette: dict[str, str] = dict(_DARK)
        self._load()

    def _load(self) -> None:
        try:
            with open(_CONFIG_FILE) as f:
                data = json.load(f)
            self._active = data.get("active", "dark")
            custom = data.get("custom", {})
            merged = dict(_DARK)
            merged.update(custom)
            self._custom = merged
        except (OSError, json.JSONDecodeError):
            self._active = "dark"

        if self._active == "custom":
            self._palette = dict(self._custom)
        else:
            self._palette = dict(BUILTIN.get(self._active, _DARK))

    @property
    def palette(self) -> dict[str, str]:
        return self._palette

    @property
    def active(self) -> str:
        return self._active

    def get(self, key: str, fallback: str = "#ffffff") -> str:
        return self._palette.get(key, fallback)

    def reload(self) -> None:
        """Re-read from disk (call if theme may have changed externally)."""
        self._load()
