"""Cancellable Story navigation, including bounded map-list scrolling."""
import re
import time

from python_macro.vision import Region

MAX_MAP_SCROLLS = 12
MAP_SCROLL_STEPS = -2
MAP_SCROLL_SETTLE = 0.3


def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def navigate_story(map_name, capture, reader, click, stop, log, timeout=30,
                   scroll=None, max_map_scrolls=MAX_MAP_SCROLLS, find_play=None):
    """Find Play -> Story -> chosen map, scrolling only when the map is absent.

    No unit placement follows this navigation yet. All clicking is delegated to
    RobloxClient.click, including hover and pre-click jitter.
    """
    if not normalize(map_name):
        raise ValueError("Choose a Story map first")
    stages = ("Play", "Story", map_name)
    if find_play is not None:
        stages = ("Story", map_name)
        deadline = time.monotonic() + timeout
        attempts = 0
        confirmed = False
        log("Searching for Play button image.")
        while not stop.is_set() and time.monotonic() < deadline and attempts < 3:
            frame = capture()
            position = find_play(frame)
            if position is None:
                if stop.wait(0.2):
                    return
                continue
            attempts += 1
            log(f"Play icon found. Clicking (attempt {attempts}/3).")
            click(position[0], position[1], frame.shape)
            if stop.is_set():
                return
            for _ in range(5):
                if stop.wait(0.25):
                    return
                frame = capture()
                matches = reader.read(
                    frame, Region(0, 0, frame.shape[1], frame.shape[0]),
                    scale=1, min_confidence=0.8,
                    accept=lambda items: any(normalize(m.text) == "story" for m in items),
                )
                if stop.is_set():
                    return
                if sum(normalize(m.text) == "story" for m in matches) == 1:
                    confirmed = True
                    log("Play click verified: Story menu visible.")
                    break
            if confirmed:
                break
            log("Play click not confirmed. Checking the image and retrying.")
        if stop.is_set():
            return
        if not confirmed:
            raise RuntimeError("Play click could not be verified: Story menu did not appear.")
    for label in stages:
        log(f"Looking for {label}.")
        deadline = time.monotonic() + timeout
        clicked = False
        missing_count, scroll_count = 0, 0
        map_list_focused = False
        while not stop.is_set() and time.monotonic() < deadline:
            frame = capture()
            matches = reader.read(
                frame, Region(0, 0, frame.shape[1], frame.shape[0]),
                scale=1, min_confidence=0.8,
                accept=lambda items: any(normalize(m.text) == normalize(label) for m in items),
            )
            candidates = [m for m in matches if normalize(m.text) == normalize(label)]
            if stop.is_set():
                return
            # Don't pick a map by guessing when OCR sees duplicate text.
            if len(candidates) == 1:
                corners = candidates[0].corners
                x = round(sum(p[0] for p in corners) / len(corners))
                y = round(sum(p[1] for p in corners) / len(corners))
                click(x, y, frame.shape)
                if stop.is_set():
                    return
                log(f"{label} clicked.")
                clicked = True
                break
            if label == map_name and scroll is not None and not candidates:
                missing_count += 1
                # Allow the Story menu to settle before interacting with its list.
                if missing_count >= 2:
                    x = frame.shape[1] // 2
                    y = min(frame.shape[0] - 1, round(frame.shape[0] * 0.86))
                    if not map_list_focused:
                        log("Selected map not visible. Focusing the lower map list.")
                        click(x, y, frame.shape)
                        if stop.is_set():
                            return
                        map_list_focused = True
                    if scroll_count >= max_map_scrolls:
                        raise RuntimeError(
                            f"Could not find {map_name} after {max_map_scrolls} downward map-list scrolls."
                        )
                    scroll(MAP_SCROLL_STEPS, x, y, frame.shape)
                    if stop.is_set():
                        return
                    scroll_count += 1
                    log(f"Scrolling map list downward ({scroll_count}/{max_map_scrolls}).")
                    if stop.wait(MAP_SCROLL_SETTLE):
                        return
                    continue
            if stop.wait(0.15):
                return
        if stop.is_set():
            return
        if not clicked:
            raise RuntimeError(f"Could not clearly find {label}. Keep its button visible and try again.")
        if stop.wait(0.35):
            return
    log("Map clicked. Story navigation stops here for now.")
