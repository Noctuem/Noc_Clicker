"""
Monitoring & execution engine.

Supports three operating modes:
  - Simple     : one trigger (image region or keystroke hold/toggle), one action
  - Sequence   : ordered list of targets; primary trigger fires the whole chain;
                 inter-target conditions control pacing; optional random-shuffle order
  - Parallel   : multiple independent trigger monitors running concurrently;
                 targets can share (link) a trigger; shared-trigger actions serialised

All screen capture and comparison runs on daemon threads; callbacks to the GUI
are dispatched via an on_status(str) callable.

Public API
----------
Engine(on_status, on_log)
  .configure_simple(cfg)
  .configure_advanced(cfg)
  .start()
  .stop()       – graceful stop, keeps GUI open
  .abort()      – same as stop (alias for global abort hotkey)
  .is_running   – property
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable, Optional

import mss
from PIL import Image

import actions
import image_compare
import window_manager as wm

# ---------------------------------------------------------------------------
# Trigger result
# ---------------------------------------------------------------------------

class _TriggerWatcher:
    """
    Watches one screen region for a trigger image.
    Calls on_fire() in a background thread when score >= threshold.
    Stops after one fire; caller restarts if needed.
    """

    def __init__(
        self,
        region: dict,          # {"left", "top", "width", "height"}
        trigger_img: Image.Image,
        threshold: float,
        poll_interval: float,
        on_fire: Callable,
    ) -> None:
        self._region        = region
        self._trigger_img   = trigger_img
        self._threshold     = threshold
        self._poll_interval = poll_interval
        self._on_fire       = on_fire
        self._stop_event    = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                shot = sct.grab(self._region)
                current = Image.frombytes("RGB", shot.size, shot.rgb)
                score = image_compare.compare(current, self._trigger_img)
                if score >= self._threshold:
                    self._stop_event.set()
                    self._on_fire()
                    return
                self._stop_event.wait(self._poll_interval)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class Engine:
    def __init__(
        self,
        on_status: Callable[[str], None],
        on_log:    Callable[[str], None],
    ) -> None:
        self._on_status  = on_status
        self._on_log     = on_log
        self._mode       = "simple"   # "simple" | "sequence" | "parallel"
        self._cfg: dict  = {}
        self._running    = False
        self._abort_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._watchers: list[_TriggerWatcher] = []
        self._action_lock = threading.Lock()  # serialise window-focus actions

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure_simple(self, cfg: dict) -> None:
        """
        cfg keys:
          trigger_type    : "image" | "keystroke"
          region          : {"left","top","width","height"}  (for image)
          trigger_img     : PIL.Image                         (for image)
          threshold       : float 0-1
          poll_interval   : float seconds
          action          : binding dict (see actions.py)
          target_hwnd     : int | None
          interval        : float seconds between repeated actions
          cooldown        : float seconds after firing before re-arming
          keystroke_mode  : "toggle" | "hold"                (for keystroke)
        """
        self._mode = "simple"
        self._cfg  = cfg

    def configure_advanced(self, cfg: dict) -> None:
        """
        cfg keys:
          adv_mode        : "sequence" | "parallel"
          targets         : list[target_dict]  (see below)
          primary_region  : {"left","top","width","height"}
          primary_img     : PIL.Image
          threshold       : float
          poll_interval   : float

        target_dict (sequence):
          action, target_hwnd, cooldown,
          pre_condition: {"type": "immediate"|"wait_time"|"wait_primary"|"wait_trigger",
                          "wait_seconds": float,
                          "region": dict, "img": PIL.Image, "threshold": float}

        target_dict (parallel):
          action, target_hwnd, cooldown,
          trigger_source  : "own" | "link:<id>"
          own_region, own_img, own_threshold   (when source=="own")
          id              : str
        """
        self._mode = "advanced"
        self._cfg  = cfg

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._abort_event.clear()

        if self._mode == "simple":
            t = threading.Thread(target=self._run_simple, daemon=True)
        elif self._cfg.get("adv_mode") == "sequence":
            t = threading.Thread(target=self._run_sequence, daemon=True)
        else:
            t = threading.Thread(target=self._run_parallel, daemon=True)

        self._threads = [t]
        t.start()

    def stop(self) -> None:
        self._abort_event.set()
        for w in self._watchers:
            w.stop()
        self._watchers.clear()
        self._running = False
        self._on_status("Stopped")

    def abort(self) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self._on_log(msg)

    def _status(self, msg: str) -> None:
        self._on_status(msg)

    def _should_stop(self) -> bool:
        return self._abort_event.is_set()

    def _fire_action(
        self,
        action: dict,
        hwnd: Optional[int],
        label: str = "",
        click_pos: Optional[tuple] = None,
    ) -> None:
        with self._action_lock:
            actions.execute(action, hwnd, click_pos=click_pos)
        self._log(f"Fired: {actions.binding_label(action)}{f'  [{label}]' if label else ''}")

    def _wait_for_trigger(
        self,
        region: dict,
        img: Image.Image,
        threshold: float,
        poll_interval: float,
    ) -> bool:
        """Block until trigger matches or abort. Returns True if matched."""
        fired = threading.Event()

        def on_fire():
            fired.set()

        w = _TriggerWatcher(region, img, threshold, poll_interval, on_fire)
        self._watchers.append(w)
        w.start()
        # Poll abort every 0.1s
        while not fired.is_set():
            if self._should_stop():
                w.stop()
                return False
            time.sleep(0.1)
        try:
            self._watchers.remove(w)
        except ValueError:
            pass
        return True

    # ------------------------------------------------------------------
    # Simple mode
    # ------------------------------------------------------------------

    def _run_simple(self) -> None:
        cfg = self._cfg
        trigger_type = cfg.get("trigger_type", "image")

        if trigger_type == "image":
            self._run_simple_image()
        else:
            self._run_simple_keystroke()

    def _run_simple_image(self) -> None:
        cfg           = self._cfg
        region        = cfg["region"]
        trigger_img   = cfg["trigger_img"]
        threshold     = cfg.get("threshold", 0.9)
        poll_interval = cfg.get("poll_interval", 0.1)
        action        = cfg.get("action")
        hwnd          = cfg.get("target_hwnd")
        cooldown      = cfg.get("cooldown", 1.0)
        click_pos     = cfg.get("click_pos")  # (x, y) or None

        self._status("Monitoring...")
        while not self._should_stop():
            matched = self._wait_for_trigger(region, trigger_img, threshold, poll_interval)
            if not matched:
                break
            self._fire_action(action, hwnd, click_pos=click_pos)
            self._status("Cooldown...")
            self._abort_event.wait(cooldown)
            if not self._should_stop():
                self._status("Monitoring...")

        if not self._should_stop():
            self._running = False
            self._status("Stopped")

    def _run_simple_keystroke(self) -> None:
        """
        Keystroke trigger is handled by the GUI's pynput listener which calls
        start/stop/abort.  This thread just fires the action repeatedly while
        running, at the configured interval.
        """
        cfg      = self._cfg
        action   = cfg.get("action")
        hwnd     = cfg.get("target_hwnd")
        interval = cfg.get("interval", 1.0)

        self._status("Active (keystroke mode)...")
        while not self._should_stop():
            self._fire_action(action, hwnd)
            self._abort_event.wait(interval)

        if not self._should_stop():
            self._running = False
            self._status("Stopped")

    # ------------------------------------------------------------------
    # Sequence mode
    # ------------------------------------------------------------------

    def _run_sequence(self) -> None:
        cfg           = self._cfg
        targets       = list(cfg.get("targets", []))
        primary_region= cfg["primary_region"]
        primary_img   = cfg["primary_img"]
        threshold     = cfg.get("threshold", 0.9)
        poll_interval = cfg.get("poll_interval", 0.1)
        random_order  = cfg.get("random_order", False)

        self._status("Waiting for primary trigger...")

        while not self._should_stop():
            # Wait for primary trigger
            matched = self._wait_for_trigger(
                primary_region, primary_img, threshold, poll_interval
            )
            if not matched:
                break

            self._log("Primary trigger detected — running sequence")

            # Determine order
            order = list(range(len(targets)))
            if random_order:
                random.shuffle(order)

            for idx in order:
                if self._should_stop():
                    break
                target = targets[idx]
                name   = target.get("name", f"Target {idx+1}")

                # Evaluate pre-condition (not used in random mode)
                if not random_order:
                    cond = target.get("pre_condition", {})
                    cond_type = cond.get("type", "immediate")

                    if cond_type == "wait_time":
                        secs = cond.get("wait_seconds", 0.0)
                        self._status(f"Waiting {secs}s before {name}...")
                        self._abort_event.wait(secs)

                    elif cond_type == "wait_primary":
                        self._status(f"Waiting for primary trigger before {name}...")
                        matched = self._wait_for_trigger(
                            primary_region, primary_img, threshold, poll_interval
                        )
                        if not matched:
                            break

                    elif cond_type == "wait_trigger":
                        self._status(f"Waiting for custom trigger before {name}...")
                        matched = self._wait_for_trigger(
                            cond["region"], cond["img"],
                            cond.get("threshold", threshold),
                            poll_interval,
                        )
                        if not matched:
                            break

                if self._should_stop():
                    break

                # Fire
                self._status(f"Firing {name}...")
                self._fire_action(target.get("action"), target.get("target_hwnd"), name)
                cooldown = target.get("cooldown", 0.0)
                if cooldown > 0:
                    self._abort_event.wait(cooldown)

            if not self._should_stop():
                self._status("Waiting for primary trigger...")

        if not self._should_stop():
            self._running = False
            self._status("Stopped")

    # ------------------------------------------------------------------
    # Parallel mode
    # ------------------------------------------------------------------

    def _run_parallel(self) -> None:
        cfg     = self._cfg
        targets = cfg.get("targets", [])
        threshold     = cfg.get("threshold", 0.9)
        poll_interval = cfg.get("poll_interval", 0.1)

        # Group targets by trigger source.
        # "own" targets each get their own watcher.
        # "link:<id>" targets are chained to the source.
        own_targets:  list[dict] = []
        link_map: dict[str, list[dict]] = {}  # source_id -> [linked targets]

        for t in targets:
            src = t.get("trigger_source", "own")
            if src == "own":
                own_targets.append(t)
            else:
                src_id = src.replace("link:", "")
                link_map.setdefault(src_id, []).append(t)

        if not own_targets:
            self._status("No targets with own triggers")
            self._running = False
            return

        self._status(f"Monitoring {len(own_targets)} trigger(s)...")

        stop_events: list[threading.Event] = []
        threads: list[threading.Thread] = []

        for t in own_targets:
            ev = threading.Event()
            stop_events.append(ev)
            linked = link_map.get(t.get("id", ""), [])
            thr = threading.Thread(
                target=self._parallel_target_loop,
                args=(t, linked, threshold, poll_interval, ev),
                daemon=True,
            )
            threads.append(thr)
            thr.start()

        # Wait for abort
        self._abort_event.wait()
        for ev in stop_events:
            ev.set()

        self._running = False
        self._status("Stopped")

    def _parallel_target_loop(
        self,
        target: dict,
        linked: list[dict],
        default_threshold: float,
        poll_interval: float,
        stop_event: threading.Event,
    ) -> None:
        region    = target.get("own_region")
        img       = target.get("own_img")
        threshold = target.get("own_threshold", default_threshold)
        name      = target.get("name", "Target")

        while not stop_event.is_set() and not self._abort_event.is_set():
            fired = threading.Event()

            def on_fire():
                fired.set()

            w = _TriggerWatcher(region, img, threshold, poll_interval, on_fire)
            self._watchers.append(w)
            w.start()

            while not fired.is_set():
                if stop_event.is_set() or self._abort_event.is_set():
                    w.stop()
                    try:
                        self._watchers.remove(w)
                    except ValueError:
                        pass
                    return
                time.sleep(0.05)

            try:
                self._watchers.remove(w)
            except ValueError:
                pass

            if stop_event.is_set() or self._abort_event.is_set():
                return

            # Fire own action first
            self._fire_action(target.get("action"), target.get("target_hwnd"), name)
            cooldown = target.get("cooldown", 0.0)
            if cooldown > 0:
                stop_event.wait(cooldown)

            # Fire linked targets in order
            for lt in linked:
                if stop_event.is_set() or self._abort_event.is_set():
                    break
                lname = lt.get("name", "Linked")
                self._fire_action(lt.get("action"), lt.get("target_hwnd"), lname)
                lc = lt.get("cooldown", 0.0)
                if lc > 0:
                    stop_event.wait(lc)
