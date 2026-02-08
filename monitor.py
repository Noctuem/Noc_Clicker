import threading
import time

import mss
import pyautogui
from PIL import Image

import image_compare


class ScreenMonitor:
    """Monitors a screen region and clicks when the trigger image is detected."""

    def __init__(self, bbox, trigger_image, click_pos, threshold=0.90,
                 poll_interval=0.1, cooldown=0.5, on_status=None):
        """
        Args:
            bbox: (x, y, width, height) absolute screen coordinates.
            trigger_image: PIL Image of the trigger state.
            click_pos: (x, y) absolute screen coordinates to click.
            threshold: similarity score (0-1) needed to fire the click.
            poll_interval: seconds between screen captures.
            cooldown: seconds to wait after clicking before resuming.
            on_status: callback(message) for status updates.
        """
        self.bbox = bbox
        self.trigger_image = trigger_image
        self.click_pos = click_pos
        self.threshold = threshold
        self.poll_interval = poll_interval
        self.cooldown = cooldown
        self.on_status = on_status

        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _report(self, msg):
        if self.on_status:
            self.on_status(msg)

    def _run(self):
        x, y, w, h = self.bbox
        region = {"left": x, "top": y, "width": w, "height": h}
        click_x, click_y = self.click_pos

        self._report("Monitoring...")

        with mss.mss() as sct:
            while self._running:
                screenshot = sct.grab(region)
                current = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

                score = image_compare.compare(current, self.trigger_image)

                if score >= self.threshold:
                    self._report(f"Trigger detected! (score: {score:.2f}) Clicking...")
                    orig_x, orig_y = pyautogui.position()
                    pyautogui.click(click_x, click_y)
                    pyautogui.moveTo(orig_x, orig_y)
                    time.sleep(self.cooldown)
                    if self._running:
                        self._report("Monitoring...")
                else:
                    time.sleep(self.poll_interval)

        self._report("Stopped.")
