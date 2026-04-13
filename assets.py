"""
Font resolution. Prefers Fira Code if installed on the system; falls back to
Consolas (always present on Windows). The resolved family is available as
FONT_FAMILY after import.
"""
import tkinter.font as tkfont


def _resolve_font() -> str:
    try:
        available = tkfont.families()
        if "Fira Code" in available:
            return "Fira Code"
    except Exception:
        pass
    return "Consolas"


FONT_FAMILY: str = _resolve_font()
