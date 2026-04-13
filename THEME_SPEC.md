# Noctuem Theme Specification

Version: 1

This document defines the shared theme format used across all noctuem_ projects.
The theme is stored at `~/.noctuem/theme.json` and can be loaded in any project
via `noctuem_theme_loader.py`.

---

## File Location

```
~/.noctuem/theme.json
```

---

## JSON Schema

```json
{
  "version": 1,
  "active": "dark",
  "custom": {
    "<colour_key>": "<hex_colour>"
  }
}
```

| Field    | Type   | Description |
|---|---|---|
| `version` | int   | Schema version (currently 1) |
| `active`  | string | Active theme name: `"dark"`, `"light"`, or `"custom"` |
| `custom`  | object | Full palette override for the `"custom"` theme |

---

## Colour Keys

All values are CSS hex colours (`#rrggbb` or `#rrggbbaa`).

### Backgrounds

| Key | Purpose |
|---|---|
| `bg_primary` | Root window / outermost background |
| `bg_secondary` | Panels, frames, main content areas |
| `bg_tertiary` | Cards, input fields, list items, elevated surfaces |
| `bg_hover` | Hover/active state for interactive surfaces |

### Accent

| Key | Purpose |
|---|---|
| `accent` | Primary brand colour — active tabs, selected indicators, focus rings |
| `accent_hover` | Lighter accent used on hover |

### Text

| Key | Purpose |
|---|---|
| `text_primary` | Main body text |
| `text_secondary` | Labels, captions, secondary information |
| `text_muted` | Disabled text, placeholders, decorative labels |

### Borders & Separators

| Key | Purpose |
|---|---|
| `border` | Widget borders, frame outlines |
| `separator` | Horizontal/vertical rule lines |

### Semantic colours

| Key | Purpose |
|---|---|
| `error` | Error messages, danger buttons |
| `success` | Success indicators |
| `warning` | Warning messages |

### Interactive widgets

| Key | Purpose |
|---|---|
| `button_bg` | Default button background |
| `button_fg` | Default button foreground |
| `entry_bg` | Text entry / combobox field background |
| `entry_fg` | Text entry foreground |
| `select_bg` | Selection highlight background |
| `select_fg` | Selection highlight foreground |
| `scrollbar` | Scrollbar thumb colour |

### Log

| Key | Purpose |
|---|---|
| `log_bg` | Log / terminal area background |
| `log_fg` | Log text colour |

---

## Typography

Font preference is stored per-project (not in `theme.json`) via `assets.py`.
The standard family preference is:

1. **Fira Code** — if installed on the system
2. **Consolas** — always available on Windows

Font sizes used in Noc projects:

| Role | Size |
|---|---|
| Small / muted label | 7–8 pt |
| Body / default | 10 pt |
| Secondary label | 9 pt |
| Header | 11 pt bold |

---

## Built-in Palettes

### Dark (default)

Based on Catppuccin Mocha — darker than VS Code Dark+.

| Key | Value |
|---|---|
| `bg_primary` | `#181825` |
| `bg_secondary` | `#1e1e2e` |
| `bg_tertiary` | `#313244` |
| `bg_hover` | `#45475a` |
| `accent` | `#cba6f7` |
| `accent_hover` | `#b4befe` |
| `text_primary` | `#cdd6f4` |
| `text_secondary` | `#a6adc8` |
| `text_muted` | `#6c7086` |
| `border` | `#45475a` |
| `error` | `#f38ba8` |
| `success` | `#a6e3a1` |
| `warning` | `#fab387` |

### Light

Based on Catppuccin Latte.

| Key | Value |
|---|---|
| `bg_primary` | `#eff1f5` |
| `bg_secondary` | `#e6e9ef` |
| `bg_tertiary` | `#dce0e8` |
| `bg_hover` | `#ccd0da` |
| `accent` | `#8839ef` |
| `accent_hover` | `#7287fd` |
| `text_primary` | `#4c4f69` |
| `text_secondary` | `#5c5f77` |
| `text_muted` | `#9ca0b0` |
| `border` | `#bcc0cc` |
| `error` | `#d20f39` |
| `success` | `#40a02b` |
| `warning` | `#fe640b` |

---

## Using in a New Project

Copy `noctuem_theme_loader.py` into your project and call:

```python
from noctuem_theme_loader import load_theme

palette = load_theme()          # returns dict of colour key → hex string
active  = load_theme.active     # "dark" | "light" | "custom"
```

Or for tkinter projects, copy `theme.py` from Noc Clicker — it applies the full
`ttk.Style` configuration automatically.
