"""
Low-level action execution: mouse clicks and key presses via Win32 SendInput.

Key binding representation (shared across the whole app)
---------------------------------------------------------
A "binding" is a dict:
    {
        "type":    "click" | "key",
        "button":  "left" | "right" | "middle",   # for click
        "mods":    ["ctrl", "shift", "alt"],        # for key (subset)
        "key":     "a",                             # for key – pynput key name
        "vk":      65,                              # resolved VK code
    }

Helper functions
----------------
binding_label(b)    -> human-readable string, e.g. "Ctrl+Shift+A" / "Left Click"
execute(b, hwnd)    – fire the action; if hwnd given, focus/restore first
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
from typing import Optional

import window_manager as wm

# ---------------------------------------------------------------------------
# Win32 structs & constants
# ---------------------------------------------------------------------------

INPUT_KEYBOARD = 1
INPUT_MOUSE    = 0

KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP   = 0x0040


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          wintypes.LONG),
        ("dy",          wintypes.LONG),
        ("mouseData",   wintypes.DWORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type",  wintypes.DWORD),
        ("_data", _INPUT_UNION),
    ]


# ---------------------------------------------------------------------------
# VK code lookup
# ---------------------------------------------------------------------------

# Modifier VK codes (left-hand variants used for injection)
_MOD_VK: dict[str, int] = {
    "ctrl":  0xA2,   # VK_LCONTROL
    "shift": 0xA0,   # VK_LSHIFT
    "alt":   0xA4,   # VK_LMENU
}

# Extended keys that need KEYEVENTF_EXTENDEDKEY
_EXTENDED_VK = {
    0xA2, 0xA3,  # L/R ctrl
    0xA4, 0xA5,  # L/R alt
    0x2D, 0x2E,  # Insert, Delete
    0x24, 0x23,  # Home, End
    0x21, 0x22,  # PgUp, PgDn
    0x26, 0x28, 0x25, 0x27,  # arrow keys
    0x2C,        # Print Screen
    0x91,        # Scroll Lock
    0x13,        # Pause
}

# pynput Key name → VK
_SPECIAL_VK: dict[str, int] = {
    "space":    0x20, "enter": 0x0D, "return": 0x0D,
    "tab":      0x09, "backspace": 0x08, "escape": 0x1B, "esc": 0x1B,
    "shift":    0xA0, "ctrl": 0xA2, "alt": 0xA4,
    "left":     0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home":     0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
    "insert":   0x2D, "delete": 0x2E,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "caps_lock": 0x14, "num_lock": 0x90, "scroll_lock": 0x91,
    "print_screen": 0x2C, "pause": 0x13,
    "media_play_pause": 0xB3, "media_next": 0xB0, "media_previous": 0xB1,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
}


def key_name_to_vk(name: str) -> int:
    """Convert a key name string to a Win32 VK code."""
    if not name:
        return 0
    low = name.lower()
    if low in _SPECIAL_VK:
        return _SPECIAL_VK[low]
    if len(name) == 1:
        vk = ctypes.windll.user32.VkKeyScanW(ord(name))
        return vk & 0xFF  # low byte is the VK code
    return 0


# ---------------------------------------------------------------------------
# Raw SendInput helpers
# ---------------------------------------------------------------------------

def _send_inputs(inputs: list[_INPUT]) -> None:
    n = len(inputs)
    arr = (_INPUT * n)(*inputs)
    ctypes.windll.user32.SendInput(n, arr, ctypes.sizeof(_INPUT))


def _key_input(vk: int, key_up: bool = False) -> _INPUT:
    flags = KEYEVENTF_KEYUP if key_up else 0
    if vk in _EXTENDED_VK:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp._data.ki.wVk = vk
    inp._data.ki.dwFlags = flags
    return inp


def _mouse_input(flags: int) -> _INPUT:
    inp = _INPUT()
    inp.type = INPUT_MOUSE
    inp._data.mi.dwFlags = flags
    return inp


# ---------------------------------------------------------------------------
# Binding helpers
# ---------------------------------------------------------------------------

def make_binding(type_: str, **kwargs) -> dict:
    """Construct a normalised binding dict."""
    b: dict = {"type": type_}
    if type_ == "click":
        b["button"] = kwargs.get("button", "left")
    else:
        b["mods"] = [m.lower() for m in kwargs.get("mods", [])]
        key = kwargs.get("key", "")
        b["key"] = key
        b["vk"]  = kwargs.get("vk") or key_name_to_vk(key)
    return b


def binding_label(b: Optional[dict]) -> str:
    """Return a human-readable label for a binding."""
    if not b:
        return "Unbound"
    if b["type"] == "click":
        return f"{b.get('button', 'left').capitalize()} Click"
    parts = [m.capitalize() for m in b.get("mods", [])]
    key = b.get("key", "")
    if key:
        parts.append(key.upper() if len(key) == 1 else key.capitalize())
    return "+".join(parts) if parts else "Unbound"


def empty_binding() -> dict:
    return {"type": "key", "mods": [], "key": "", "vk": 0}


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

def execute(binding: Optional[dict], target_hwnd: Optional[int] = None) -> None:
    """
    Fire the action described by *binding*.

    If *target_hwnd* is given:
      - Save current foreground window
      - Focus / restore target window
      - Send the input
      - Restore previous window focus
    """
    if not binding:
        return

    prev_hwnd: Optional[int] = None
    needs_focus = target_hwnd and wm.is_window_valid(target_hwnd)

    if needs_focus:
        prev_hwnd = wm.get_foreground_hwnd()
        wm.focus_window(target_hwnd)
        time.sleep(0.04)  # allow window to come to foreground

    try:
        if binding["type"] == "click":
            _do_click(binding.get("button", "left"))
        else:
            _do_key(binding.get("mods", []), binding.get("vk", 0))
    finally:
        if needs_focus and prev_hwnd:
            time.sleep(0.02)
            wm.restore_focus(prev_hwnd)


def _do_click(button: str) -> None:
    pairs = {
        "left":   (MOUSEEVENTF_LEFTDOWN,   MOUSEEVENTF_LEFTUP),
        "right":  (MOUSEEVENTF_RIGHTDOWN,  MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }
    down_flag, up_flag = pairs.get(button, pairs["left"])
    _send_inputs([_mouse_input(down_flag), _mouse_input(up_flag)])


def _do_key(mods: list[str], vk: int) -> None:
    if not vk:
        return
    inputs: list[_INPUT] = []
    # Press modifiers
    for mod in mods:
        mod_vk = _MOD_VK.get(mod)
        if mod_vk:
            inputs.append(_key_input(mod_vk))
    # Press + release main key
    inputs.append(_key_input(vk))
    inputs.append(_key_input(vk, key_up=True))
    # Release modifiers in reverse
    for mod in reversed(mods):
        mod_vk = _MOD_VK.get(mod)
        if mod_vk:
            inputs.append(_key_input(mod_vk, key_up=True))
    _send_inputs(inputs)
