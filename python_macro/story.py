"""Cancellable Story lobby navigation. Stops after the selected map click."""
import re
import time

from python_macro.vision import Region


def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def navigate_story(map_name, capture, reader, click, stop, log, timeout=30):
    if not normalize(map_name):
        raise ValueError("Choose a Story map first")
    for label in ("Play", "Story", map_name):
        log(f"Looking for {label}.")
        deadline = time.monotonic() + timeout
        clicked = False
        while not stop.is_set() and time.monotonic() < deadline:
            frame = capture()
            matches = reader.read(frame, Region(0, 0, frame.shape[1], frame.shape[0]),
                                  scale=1, min_confidence=0.8,
                                  accept=lambda items: any(normalize(m.text) == normalize(label) for m in items))
            candidates = [m for m in matches if normalize(m.text) == normalize(label)]
            if stop.is_set():
                return
            # Never guess between duplicate labels or use stale fixed coordinates.
            if len(candidates) == 1:
                corners = candidates[0].corners
                x = round(sum(p[0] for p in corners) / len(corners))
                y = round(sum(p[1] for p in corners) / len(corners))
                click(x, y, frame.shape)
                log(f"{label} clicked.")
                clicked = True
                break
            stop.wait(0.15)
        if stop.is_set():
            return
        if not clicked:
            raise RuntimeError(f"Could not clearly find {label}. Keep its button visible and try again.")
        if stop.wait(0.35):
            return
    log("Map clicked. Story navigation stops here for now.")
