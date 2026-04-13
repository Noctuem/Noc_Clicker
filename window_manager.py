"""
Win32 window enumeration and focus management via ctypes only (no pywin32).

Public API
----------
get_all_windows()           -> list[tuple[int, str]]   (hwnd, title)
get_foreground_hwnd()       -> int
focus_window(hwnd)          – bring to front, restore if minimised
restore_focus(hwnd)         – SetForegroundWindow without ShowWindow
is_window_valid(hwnd)       -> bool
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------
SW_RESTORE = 9
GW_OWNER    = 4

_user32 = ctypes.windll.user32

# Callback type for EnumWindows
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_window_title(hwnd: int) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _is_alt_tab_window(hwnd: int) -> bool:
    """Approximate the same filter as Alt+Tab uses."""
    if not _user32.IsWindowVisible(hwnd):
        return False
    # Skip windows with an owner (owned tool windows, etc.)
    if _user32.GetWindow(hwnd, GW_OWNER):
        return False
    # Skip windows with WS_EX_TOOLWINDOW style
    WS_EX_TOOLWINDOW = 0x00000080
    ex_style = _user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    if ex_style & WS_EX_TOOLWINDOW:
        return False
    return True


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def get_all_windows() -> list[tuple[int, str]]:
    """Return (hwnd, title) for every visible, titled top-level window."""
    results: list[tuple[int, str]] = []

    def _cb(hwnd: int, _: int) -> bool:
        if _is_alt_tab_window(hwnd):
            title = _get_window_title(hwnd)
            if title:
                results.append((hwnd, title))
        return True

    _user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    results.sort(key=lambda x: x[1].lower())
    return results


def get_foreground_hwnd() -> int:
    return _user32.GetForegroundWindow()


def is_window_valid(hwnd: int) -> bool:
    return bool(_user32.IsWindow(hwnd))


def focus_window(hwnd: int) -> None:
    """Restore (if minimised) and bring the window to the foreground."""
    if not is_window_valid(hwnd):
        return
    # IsIconic = minimised
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.SetForegroundWindow(hwnd)


def restore_focus(hwnd: int) -> None:
    """Return focus to a previously active window without un-minimising."""
    if hwnd and is_window_valid(hwnd):
        _user32.SetForegroundWindow(hwnd)
