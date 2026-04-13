"""
Profile persistence.

Directory layout
----------------
profiles/
  <profile_name>/
    settings.json
    triggers/
      primary.png
      <target_id>.png
      <target_id>_condition.png   (for wait_trigger conditions)

Coordinate convention
---------------------
All screen regions are stored monitor-relative so profiles are portable across
different resolutions:
  {
    "monitor_idx": 0,           # index into mss monitors list (1-based, 0=virtual)
    "rx": 0.1,  "ry": 0.1,     # top-left as fraction of monitor w/h
    "rw": 0.2,  "rh": 0.05,    # size as fraction of monitor w/h
  }

At load time these are resolved back to absolute pixel coordinates using the
current monitor layout.

Public API
----------
PROFILES_DIR                          – Path to profiles/
list_profiles()   -> list[str]
save_profile(name, state)
load_profile(name) -> dict | None
delete_profile(name)
region_to_relative(abs_region, monitors) -> dict
region_to_absolute(rel_region, monitors) -> dict
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

import mss
from PIL import Image

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROFILES_DIR = Path(__file__).parent / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _get_monitors() -> list[dict]:
    with mss.mss() as sct:
        # sct.monitors[0] is virtual screen, [1..] are real monitors
        return list(sct.monitors)


def region_to_relative(abs_region: dict, monitors: Optional[list[dict]] = None) -> dict:
    """
    Convert an absolute pixel region {"left","top","width","height"} to a
    monitor-relative dict.  Picks the monitor whose area most overlaps the region.
    """
    if monitors is None:
        monitors = _get_monitors()

    real_monitors = monitors[1:]  # skip virtual
    if not real_monitors:
        # Fallback: use virtual screen (index 0)
        vm = monitors[0]
        return {
            "monitor_idx": 0,
            "rx": (abs_region["left"]  - vm["left"]) / max(vm["width"],  1),
            "ry": (abs_region["top"]   - vm["top"])  / max(vm["height"], 1),
            "rw": abs_region["width"]  / max(vm["width"],  1),
            "rh": abs_region["height"] / max(vm["height"], 1),
        }

    # Find best-matching monitor
    best_idx = 1
    best_overlap = -1
    rx = abs_region["left"]
    ry = abs_region["top"]
    rr = rx + abs_region["width"]
    rb = ry + abs_region["height"]

    for i, m in enumerate(real_monitors, start=1):
        mx, my = m["left"], m["top"]
        mr, mb = mx + m["width"], my + m["height"]
        overlap = max(0, min(rr, mr) - max(rx, mx)) * max(0, min(rb, mb) - max(ry, my))
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx     = i

    mon = monitors[best_idx]
    return {
        "monitor_idx": best_idx,
        "rx": (abs_region["left"]  - mon["left"]) / max(mon["width"],  1),
        "ry": (abs_region["top"]   - mon["top"])  / max(mon["height"], 1),
        "rw": abs_region["width"]  / max(mon["width"],  1),
        "rh": abs_region["height"] / max(mon["height"], 1),
    }


def region_to_absolute(rel_region: dict, monitors: Optional[list[dict]] = None) -> dict:
    """Convert a monitor-relative region back to absolute pixel coordinates."""
    if monitors is None:
        monitors = _get_monitors()

    idx = rel_region.get("monitor_idx", 1)
    if idx >= len(monitors):
        idx = min(1, len(monitors) - 1)
    mon = monitors[idx]

    return {
        "left":   int(rel_region["rx"] * mon["width"]  + mon["left"]),
        "top":    int(rel_region["ry"] * mon["height"] + mon["top"]),
        "width":  max(1, int(rel_region["rw"] * mon["width"])),
        "height": max(1, int(rel_region["rh"] * mon["height"])),
    }


# ---------------------------------------------------------------------------
# Profile I/O
# ---------------------------------------------------------------------------

def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    return sorted(
        p.name for p in PROFILES_DIR.iterdir()
        if p.is_dir() and (p / "settings.json").exists()
    )


def _profile_dir(name: str) -> Path:
    return PROFILES_DIR / name


def save_profile(name: str, state: dict) -> None:
    """
    state is the full GUI state dict.  Images are PIL Images stored in state;
    they are extracted, saved as PNGs, and replaced by relative paths in the JSON.
    """
    pdir = _profile_dir(name)
    tdir = pdir / "triggers"
    pdir.mkdir(parents=True, exist_ok=True)
    tdir.mkdir(exist_ok=True)

    # Deep-copy the state, extracting PIL Images to files
    serialisable = _serialise_state(state, tdir)

    with open(pdir / "settings.json", "w") as f:
        json.dump(serialisable, f, indent=2)


def load_profile(name: str) -> Optional[dict]:
    """
    Load a profile.  PIL Images are loaded back from the trigger PNG files.
    Returns None if the profile doesn't exist or is corrupt.
    """
    pdir = _profile_dir(name)
    settings_path = pdir / "settings.json"
    if not settings_path.exists():
        return None
    try:
        with open(settings_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    tdir = pdir / "triggers"
    _deserialise_state(data, tdir)
    return data


def delete_profile(name: str) -> None:
    pdir = _profile_dir(name)
    if pdir.exists():
        shutil.rmtree(pdir)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialise_state(state: dict, tdir: Path) -> dict:
    """
    Walk the state dict, replacing PIL Image values with {"__img__": filename}.
    Saves the images to tdir.
    """
    import copy
    result = copy.deepcopy(state)
    _walk_serialise(result, tdir)
    return result


def _walk_serialise(obj, tdir: Path) -> None:
    if isinstance(obj, dict):
        keys = list(obj.keys())
        for k in keys:
            v = obj[k]
            if isinstance(v, Image.Image):
                fname = f"{uuid.uuid4().hex}.png"
                v.save(tdir / fname)
                obj[k] = {"__img__": fname}
            elif isinstance(v, (dict, list)):
                _walk_serialise(v, tdir)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, Image.Image):
                fname = f"{uuid.uuid4().hex}.png"
                item.save(tdir / fname)
                obj[i] = {"__img__": fname}
            elif isinstance(item, (dict, list)):
                _walk_serialise(item, tdir)


def _deserialise_state(obj, tdir: Path) -> None:
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, dict) and "__img__" in v:
                path = tdir / v["__img__"]
                try:
                    obj[k] = Image.open(path).convert("RGB")
                except OSError:
                    obj[k] = None
            elif isinstance(v, (dict, list)):
                _deserialise_state(v, tdir)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, dict) and "__img__" in item:
                path = tdir / item["__img__"]
                try:
                    obj[i] = Image.open(path).convert("RGB")
                except OSError:
                    obj[i] = None
            elif isinstance(item, (dict, list)):
                _deserialise_state(item, tdir)
