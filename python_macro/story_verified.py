"""Verified, cancellable Story navigation for the live Anime Expeditions worker.

Never interpret SendInput acceptance alone as navigation success: re-capture
the client, look for the next screen, and re-detect before any retry.
"""
import time

import cv2
import numpy as np

from python_macro.story import (
    MAP_SCROLL_SETTLE, MAP_SCROLL_STEPS, MAX_MAP_SCROLLS,
    is_act_label, normalize, validate_act, validate_difficulty,
)
from python_macro.vision import Region


def changed_screen(before, after, fraction=0.075):
    """Detect a substantial UI transition, not tiny cursor/hover changes."""
    if before.shape != after.shape or before.size == 0:
        return False
    def thumbnail(frame):
        image = frame[:, :, :3] if frame.ndim == 3 else frame
        return cv2.resize(image, (160, 100), interpolation=cv2.INTER_AREA)
    a, b = thumbnail(before), thumbnail(after)
    delta = cv2.absdiff(a, b)
    change = np.max(delta, axis=2) if delta.ndim == 3 else delta
    return bool(np.mean(change > 40) >= fraction)


def click_and_confirm(label, locate, advanced, capture, click, stop, log,
                      highlight=None, timeout=30, attempts=3, settle_seconds=1.5):
    """Click a freshly detected target, then check a real screen transition.

    locate(frame) -> (x,y[,confidence]) or None.
    advanced(after,before) -> whether the game entered the expected next state.
    Stops without clicking if the button is missing; never reuses stale coords.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while not stop.is_set() and time.monotonic() < deadline:
        before = capture()
        target = locate(before)
        if stop.is_set():
            return False
        if target is None:
            if stop.wait(0.10):
                return False
            continue
        if attempt >= attempts:
            raise RuntimeError(f"{label} did not advance after {attempts} verified click attempts.")
        x, y = int(target[0]), int(target[1])
        attempt += 1
        if highlight is not None:
            highlight(x, y, before.shape)
        log(f"{label}: click attempt {attempt}/{attempts} at ({x}, {y}).")
        if stop.is_set() or click(x, y, before.shape) is False:
            return False
        until = min(deadline, time.monotonic() + settle_seconds)
        while not stop.is_set() and time.monotonic() < until:
            after = capture()
            if advanced(after, before):
                log(f"{label}: navigation confirmed.")
                return True
            if stop.wait(0.10):
                return False
        if stop.is_set():
            return False
        log(f"{label}: no confirmed transition; searching again before retry.")
    if stop.is_set():
        return False
    raise RuntimeError(f"Timed out waiting for {label} to appear or advance.")


class FastText:
    """One OCR pass per captured image; periodic higher-quality recovery."""

    def __init__(self, reader, stop):
        self.reader, self.stop = reader, stop
        self.last_frame, self.matches = None, []
        self.scans = 0

    def unique(self, frame, predicate):
        if frame is not self.last_frame:
            self.last_frame = frame
            self.scans += 1
            thorough = self.scans % 5 == 0
            self.matches = self.reader.read(
                frame, Region(0, 0, frame.shape[1], frame.shape[0]),
                scale=2 if thorough else 1,
                max_variants=3 if thorough else 1,
                min_confidence=0.65,
                cancelled=self.stop.is_set,
            )
        options = [m for m in self.matches if predicate(m.text)]
        if len(options) != 1:
            return None
        points = options[0].corners
        return (round(sum(p[0] for p in points) / len(points)),
                round(sum(p[1] for p in points) / len(points)))


def navigate_story_checked(map_name, capture, reader, click, stop, log, timeout=30,
                           scroll=None, max_map_scrolls=MAX_MAP_SCROLLS, find_play=None,
                           skip_play=False, act_name=None, difficulty="Normal",
                           find_act=None, find_start=None, highlight=None):
    if not normalize(map_name):
        raise ValueError("Choose a Story map first.")
    act = validate_act(act_name) if act_name is not None else None
    if act not in (None, "Mastery", "Infinite"):
        validate_difficulty(difficulty)
    ocr = FastText(reader, stop)

    def text_target(label):
        return lambda frame: ocr.unique(frame, lambda t: normalize(t) == normalize(label))

    def act_target(frame):
        if find_act is not None:
            return find_act(frame, act)
        return ocr.unique(frame, lambda t: is_act_label(t, act))

    def press(label, locate, advanced):
        return click_and_confirm(label, locate, advanced, capture, click, stop, log,
                                 highlight=highlight, timeout=timeout)

    if not skip_play:
        log("Opening Play menu.")
        if not press("Play", find_play if find_play is not None else text_target("Play"),
                     lambda after, before: text_target("Story")(after) is not None):
            return
    log("Selecting Story.")
    if not press("Story", text_target("Story"),
                 lambda after, before: text_target(map_name)(after) is not None
                 or (text_target("Story")(after) is None and changed_screen(before, after))):
        return

    log(f"Finding map: {map_name}.")
    deadline = time.monotonic() + timeout
    missing, scrolls, focused = 0, 0, False
    while not stop.is_set() and time.monotonic() < deadline:
        frame = capture()
        target = text_target(map_name)(frame)
        if stop.is_set():
            return
        if target is not None:
            if not press(map_name, text_target(map_name),
                         lambda after, before:
                         (act is not None and act_target(after) is not None)
                         or (text_target(map_name)(after) is None and changed_screen(before, after))):
                return
            break
        missing += 1
        if scroll is not None and missing >= 2:
            x, y = frame.shape[1] // 2, min(frame.shape[0] - 1, round(frame.shape[0] * 0.86))
            if not focused:
                if highlight is not None:
                    highlight(x, y, frame.shape)
                if click(x, y, frame.shape) is False:
                    return
                focused = True
            if scrolls >= max_map_scrolls:
                raise RuntimeError(f"Could not find {map_name} after {max_map_scrolls} downward map-list scrolls.")
            scroll(MAP_SCROLL_STEPS, x, y, frame.shape)
            scrolls += 1
            if stop.wait(MAP_SCROLL_SETTLE):
                return
        elif stop.wait(0.10):
            return
    else:
        if stop.is_set():
            return
        raise RuntimeError(f"Could not uniquely identify map {map_name}.")
    if stop.is_set():
        return
    if act is None:
        log("Story map selected. Ready for act selection.")
        return

    log(f"Selecting {act}.")
    if not press(act, act_target,
                 lambda after, before:
                 changed_screen(before, after, fraction=0.02)
                 and text_target("Select Stage")(after) is not None):
        return
    if act not in ("Mastery", "Infinite"):
        if difficulty == "Hard":
            log("Selecting Hard difficulty.")
            if not press("Hard", text_target("Hard"),
                         lambda after, before: changed_screen(before, after, fraction=0.015)):
                return
        else:
            log("Normal difficulty.")

    log("Selecting stage.")
    if not press("Select Stage", text_target("Select Stage"),
                 lambda after, before:
                 (find_start(after) is not None if find_start is not None
                  else text_target("Start")(after) is not None)):
        return
    log("Starting Story.")
    start_locator = find_start if find_start is not None else text_target("Start")
    if not press("Start", start_locator,
                 lambda after, before:
                 start_locator(after) is None and changed_screen(before, after, fraction=0.05)):
        return
    log("Start confirmed. Waiting for the game to load.")
