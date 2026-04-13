"""
Global hotkey management via pynput.

Tracks which modifier keys (ctrl / shift / alt) are currently held and fires
registered callbacks when a matching key combo is pressed.

Key representation
------------------
A hotkey combo is stored as (frozenset_of_mods, vk_int).
  mods  : subset of {"ctrl", "shift", "alt"}
  vk    : Win32 VK code for the trigger key (non-modifier)

Public API
----------
HotkeyManager()
  .register(mods, vk, callback, name=None)
  .unregister(mods, vk)
  .start()
  .stop()
  .has_conflict(mods, vk) -> bool
  .all_bindings() -> list[tuple[frozenset, int, str]]

Conflict detection
------------------
Two bindings conflict if their (mods, vk) tuples are identical.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from pynput import keyboard as kb

# ---------------------------------------------------------------------------
# Modifier normalisation
# ---------------------------------------------------------------------------

_MOD_KEYS = {
    kb.Key.ctrl,   kb.Key.ctrl_l,  kb.Key.ctrl_r,
    kb.Key.shift,  kb.Key.shift_l, kb.Key.shift_r,
    kb.Key.alt,    kb.Key.alt_l,   kb.Key.alt_r,
    kb.Key.alt_gr,
}

_KEY_TO_MOD: dict = {
    kb.Key.ctrl:    "ctrl",  kb.Key.ctrl_l:  "ctrl",  kb.Key.ctrl_r:  "ctrl",
    kb.Key.shift:   "shift", kb.Key.shift_l: "shift", kb.Key.shift_r: "shift",
    kb.Key.alt:     "alt",   kb.Key.alt_l:   "alt",   kb.Key.alt_r:   "alt",
    kb.Key.alt_gr:  "alt",
}


def _pynput_to_vk(key) -> int:
    """Extract a Win32 VK code from a pynput key object."""
    try:
        # KeyCode with vk attribute (most keys)
        if hasattr(key, "vk") and key.vk:
            return key.vk
        # pynput special Key enum
        if hasattr(key, "value") and hasattr(key.value, "vk"):
            return key.value.vk
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# HotkeyManager
# ---------------------------------------------------------------------------

class HotkeyManager:
    def __init__(self) -> None:
        self._lock    = threading.Lock()
        # (frozenset_mods, vk) -> (callback, name)
        self._bindings: dict[tuple, tuple[Callable, str]] = {}
        self._pressed_mods: set[str] = set()
        self._listener: Optional[kb.Listener] = None
        self._running = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        mods: list[str],
        vk: int,
        callback: Callable,
        name: str = "",
    ) -> None:
        key = (frozenset(m.lower() for m in mods), vk)
        with self._lock:
            self._bindings[key] = (callback, name)

    def unregister(self, mods: list[str], vk: int) -> None:
        key = (frozenset(m.lower() for m in mods), vk)
        with self._lock:
            self._bindings.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._bindings.clear()

    def has_conflict(self, mods: list[str], vk: int) -> bool:
        key = (frozenset(m.lower() for m in mods), vk)
        with self._lock:
            return key in self._bindings

    def all_bindings(self) -> list[tuple[frozenset, int, str]]:
        with self._lock:
            return [(k[0], k[1], v[1]) for k, v in self._bindings.items()]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._pressed_mods.clear()
        self._listener = kb.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self._listener.start()

    def stop(self) -> None:
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._pressed_mods.clear()

    # ------------------------------------------------------------------
    # Listener callbacks
    # ------------------------------------------------------------------

    def _on_press(self, key) -> None:
        if not self._running:
            return

        mod = _KEY_TO_MOD.get(key)
        if mod:
            self._pressed_mods.add(mod)
            return

        vk = _pynput_to_vk(key)
        if not vk:
            return

        combo = (frozenset(self._pressed_mods), vk)
        with self._lock:
            entry = self._bindings.get(combo)
        if entry:
            callback, _ = entry
            # Fire on a daemon thread so we don't block the listener
            t = threading.Thread(target=callback, daemon=True)
            t.start()

    def _on_release(self, key) -> None:
        mod = _KEY_TO_MOD.get(key)
        if mod:
            self._pressed_mods.discard(mod)


# ---------------------------------------------------------------------------
# One-shot capture (used by the binding widget)
# ---------------------------------------------------------------------------

class BindingCapture:
    """
    Captures the next non-modifier key press (with current modifiers) from
    the global keyboard.  Call .start(callback) once; callback receives
    (mods: list[str], vk: int, key_name: str).
    Call .cancel() to abort.
    """

    def __init__(self) -> None:
        self._listener: Optional[kb.Listener] = None
        self._callback: Optional[Callable] = None
        self._mods: set[str] = set()
        self._done = False

    def start(self, callback: Callable) -> None:
        self._callback = callback
        self._mods.clear()
        self._done = False
        self._listener = kb.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self._listener.start()

    def cancel(self) -> None:
        self._done = True
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        if self._done:
            return
        mod = _KEY_TO_MOD.get(key)
        if mod:
            self._mods.add(mod)
            return
        # Escape cancels
        if key == kb.Key.esc:
            self.cancel()
            return

        vk = _pynput_to_vk(key)
        key_name = _key_display_name(key)
        self._done = True
        mods = list(self._mods)
        if self._listener:
            self._listener.stop()
            self._listener = None
        if self._callback:
            t = threading.Thread(
                target=self._callback,
                args=(mods, vk, key_name),
                daemon=True,
            )
            t.start()

    def _on_release(self, key) -> None:
        mod = _KEY_TO_MOD.get(key)
        if mod:
            self._mods.discard(mod)


def _key_display_name(key) -> str:
    """Return a short human-readable name for a pynput key."""
    _SPECIAL_NAMES = {
        kb.Key.space:       "Space",
        kb.Key.enter:       "Enter",
        kb.Key.tab:         "Tab",
        kb.Key.backspace:   "Backspace",
        kb.Key.delete:      "Delete",
        kb.Key.insert:      "Insert",
        kb.Key.home:        "Home",
        kb.Key.end:         "End",
        kb.Key.page_up:     "PgUp",
        kb.Key.page_down:   "PgDn",
        kb.Key.up:          "Up",
        kb.Key.down:        "Down",
        kb.Key.left:        "Left",
        kb.Key.right:       "Right",
        kb.Key.f1:  "F1",  kb.Key.f2:  "F2",  kb.Key.f3:  "F3",
        kb.Key.f4:  "F4",  kb.Key.f5:  "F5",  kb.Key.f6:  "F6",
        kb.Key.f7:  "F7",  kb.Key.f8:  "F8",  kb.Key.f9:  "F9",
        kb.Key.f10: "F10", kb.Key.f11: "F11", kb.Key.f12: "F12",
        kb.Key.caps_lock:   "CapsLock",
        kb.Key.num_lock:    "NumLock",
        kb.Key.scroll_lock: "ScrollLock",
        kb.Key.print_screen:"PrintScrn",
        kb.Key.pause:       "Pause",
        kb.Key.esc:         "Esc",
    }
    if key in _SPECIAL_NAMES:
        return _SPECIAL_NAMES[key]
    try:
        c = key.char
        if c:
            return c.upper()
    except AttributeError:
        pass
    return str(key)
