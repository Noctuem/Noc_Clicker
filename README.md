# Noc Clicker

An image-triggered auto-clicker and key-sender for Windows.  Watch a region of
your screen; when it matches a captured "trigger" image, automatically fire a
mouse click or key press — with full modifier support, multi-target sequencing,
and parallel execution.

**Created by noctuem_** · MIT License

---

## Features

| Feature | Details |
|---|---|
| Image trigger | Capture a screen region; fire when it matches your trigger screenshot |
| Keystroke trigger | Hold or toggle a hotkey to start firing |
| Click or key press | Fire left / right / middle click, or any key combo (`Ctrl+Shift+P`, etc.) |
| Window targeting | Pick a window from a dropdown; Noc Clicker focuses it, fires the key, then restores focus |
| Simple mode | One trigger → one action. Fast to set up |
| Advanced sequence | Ordered list of targets fired in one pass; optional per-step wait conditions |
| Advanced parallel | Multiple independent trigger watchers running concurrently |
| Global hotkeys | Start/Stop and Abort binds work even when Noc Clicker is in the background |
| Profiles | Save/load everything (settings, trigger images, theme) to `profiles/<name>/` |
| Dark / light theme | Ships dark by default; one-click toggle; fully customisable colour editor |
| Click history log | Timestamped log of every trigger fire and action |

---

## Requirements

- Windows 10 / 11
- Python 3.10+
- [Fira Code](https://github.com/tonsky/FiraCode/releases) font *(optional — falls back to Consolas)*

Install dependencies:

```
pip install -r requirements.txt
```

---

## Running

```
python main.py
```

or double-click `run.bat`.

---

## Quick Start — Simple Mode

1. **Select Region & Capture** — drag a rectangle around the area you want to watch.
   The captured screenshot becomes your *trigger image*.
2. Set **Similarity** threshold (default 90%).  Higher = stricter match required.
3. Set **Action** — click the binding box and press a key or click a mouse button.
4. *(Optional)* pick a **Target Window** if the action should be sent to a specific app.
5. Tune **Interval** (time between repeated fires) and **Cooldown** (pause after each fire).
6. Press **Start** (or your configured Start/Stop hotkey).

### Keystroke trigger (Simple mode)

Switch Trigger to **Keystroke**, bind a key, and choose **Toggle** or **Hold**:

- **Toggle** — press once to start auto-firing, press again to stop.
- **Hold** — fires while the key is held down; stops on release.

---

## Advanced Mode — Sequence

The primary trigger fires the **entire target list** top-to-bottom (or in
shuffled order if **Random** is selected).

> **Random note:** in Random order, every target fires exactly once in a random
> order before any target repeats — like shuffling a deck of cards.

### Inter-target conditions

Each target can have a **Wait** condition that runs *before* that target fires:

| Condition | Behaviour |
|---|---|
| Nothing (immediate) | Fire immediately after the previous target |
| Time | Wait N seconds |
| Primary trigger again | Pause and wait for the primary trigger to fire again |
| New trigger image | Pause and wait for a different image to appear |

---

## Advanced Mode — Parallel

Each target monitors its own trigger independently in a background thread.

- A target can **link** its trigger to another target — it will fire its action
  whenever the source target's trigger fires (chained), using only one monitor thread.
- When multiple targets share a trigger, their actions fire in list order (serialised)
  to avoid window-focus conflicts.

---

## Binding Keys / Actions

Click any **binding box** (hotkeys, action, or per-target action):

1. The box shows **"Press a key or click…"**
2. Hold any modifiers (Ctrl, Shift, Alt) and press your desired key.
   For action bindings you can also click a mouse button.
3. The binding is set immediately.  Press **Escape** to cancel.

Modifier keys tracked: **Ctrl**, **Shift**, **Alt** (left and right both count).

---

## Global Hotkeys

Set in the **Global Hotkeys** panel (always visible at the bottom):

| Hotkey | Effect |
|---|---|
| Start / Stop | Toggle monitoring on/off without touching the GUI |
| Abort | Immediately stop all automation; keeps the app open |

> If Start/Stop and Abort are bound to the same combo, a warning is shown.

---

## Profiles

**File → Save Profile** — enter a name.  Saved to `profiles/<name>/`:

```
profiles/
  my_profile/
    settings.json       ← all settings including theme
    triggers/
      *.png             ← captured trigger images
```

Regions are stored **monitor-relative** (fraction of monitor width/height), so
profiles shared between a 4K and 1080p machine will map correctly as long as the
target content is in the same relative screen position.

**File → Load Profile…** — pick from a list of saved profiles.

---

## Theme

**View → Dark Theme / Light Theme / Custom Theme**

**View → Edit Theme…** opens the colour editor — click any swatch to open a
full HSV colour wheel + RGBA sliders + hex input.  Changes apply live.  Save
with **"Save as Custom"** to persist.

Theme preference is saved globally to `~/.noctuem/theme.json` and shared across
all Noc projects.

---

## Window Focus Behaviour

When a target window is set:

1. Current foreground window is saved.
2. If the target window is minimised, it is **restored** (not re-minimised after).
3. The key/click is sent.
4. Focus is returned to the previously active window.

If "Any window" is selected, the input is sent to whatever window currently has focus.

---

## File Overview

| File | Purpose |
|---|---|
| `main.py` | Entry point, DPI awareness |
| `gui.py` | Main window, Simple/Advanced panels, menus |
| `widgets.py` | Custom widgets: BindingBox, ColorPicker, TargetItem, TargetList |
| `engine.py` | Monitoring and execution engine (simple / sequence / parallel) |
| `actions.py` | Win32 mouse click and key press via SendInput |
| `hotkey.py` | Global hotkey listener via pynput |
| `window_manager.py` | Win32 window enumeration and focus management |
| `image_compare.py` | MSE-based image similarity (0–1 score) |
| `region_selector.py` | Full-screen drag-to-select overlay |
| `profile.py` | Profile save/load with monitor-relative coordinates |
| `theme.py` | Theme system and ttk styling |
| `assets.py` | Font detection (Fira Code → Consolas fallback) |

---

## License

MIT — see [LICENSE](LICENSE).
