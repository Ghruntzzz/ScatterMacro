"""Cancellable Anime Expeditions Story navigation with the verified mouse method.

Play -> Story -> Map -> Act -> Difficulty (Acts 1-5) -> Select Stage -> Start.
The live worker supplies the dashboard's saved act and difficulty settings.
"""
import re
import time

from python_macro.vision import Region

MAX_MAP_SCROLLS = 12
MAP_SCROLL_STEPS = -3
MAP_SCROLL_SETTLE = 0.09


def normalize(text):
    return re.sub(r"[^a-z0-9]", "", str(text).casefold())


def validate_act(value):
    if value in ("Mastery", "Infinite"):
        return value
    match = re.fullmatch(r"Act\s*([1-5])", str(value).strip(), re.IGNORECASE)
    if match:
        return f"Act {match.group(1)}"
    raise ValueError("Story act must be Act 1-5, Mastery, or Infinite.")


def validate_difficulty(value):
    if value not in ("Normal", "Hard"):
        raise ValueError("Story difficulty must be Normal or Hard.")
    return value


def is_act_label(text, act):
    """Recognize act tiles, not arbitrary partial words or numbers."""
    clean = normalize(text)
    if act == "Mastery":
        return clean in ("m", "mastery")
    if act == "Infinite":
        return text.strip() in ("∞", "♾", "♾️") or clean in ("infinite", "infinity")
    number = act[-1]
    return clean in (number, "act" + number)


def read_targets(frame, reader, predicate):
    matches = reader.read(
        frame, Region(0, 0, frame.shape[1], frame.shape[0]),
        scale=2, min_confidence=0.65,
        accept=lambda found: any(predicate(match.text) for match in found),
    )
    return [match for match in matches if predicate(match.text)]


def click_match(candidate, frame, click, stop):
    x = round(sum(p[0] for p in candidate.corners) / len(candidate.corners))
    y = round(sum(p[1] for p in candidate.corners) / len(candidate.corners))
    sent = click(x, y, frame.shape)
    return not stop.is_set() and sent is not False


def select_text(label, predicate, capture, reader, click, stop, timeout):
    """Wait for exactly one matching UI label and click its center."""
    deadline = time.monotonic() + timeout
    while not stop.is_set() and time.monotonic() < deadline:
        frame = capture()
        options = read_targets(frame, reader, predicate)
        if stop.is_set():
            return False
        if len(options) == 1:
            return click_match(options[0], frame, click, stop)
        if stop.wait(0.08):
            return False
    if stop.is_set():
        return False
    raise RuntimeError(
        f"Could not uniquely identify {label}. A screenshot of this screen "
        "would help refine recognition."
    )


def navigate_story(map_name, capture, reader, click, stop, log, timeout=30,
                   scroll=None, max_map_scrolls=MAX_MAP_SCROLLS, find_play=None,
                   skip_play=False, act_name=None, difficulty="Normal"):
    """Navigate using captured Roblox client coordinates and cancellable input.

    act_name=None retains the legacy map-only contract for existing callers;
    the live Story worker always supplies the selected dashboard act.
    """
    if not normalize(map_name):
        raise ValueError("Choose a Story map first.")
    act = validate_act(act_name) if act_name is not None else None
    if act is not None and act not in ("Mastery", "Infinite"):
        validate_difficulty(difficulty)

    if not skip_play:
        log("Opening Play menu.")
        if find_play is None:
            if not select_text("Play", lambda t: normalize(t) == "play",
                               capture, reader, click, stop, timeout):
                return
        else:
            deadline = time.monotonic() + timeout
            confirmed = False
            attempts = 0
            while not stop.is_set() and time.monotonic() < deadline and attempts < 3:
                frame = capture()
                location = find_play(frame)
                if location is None:
                    if stop.wait(0.15):
                        return
                    continue
                attempts += 1
                sent = click(int(location[0]), int(location[1]), frame.shape)
                if stop.is_set() or sent is False:
                    return
                # A sent mouse event is not proof Roblox opened the menu.
                for _ in range(6):
                    if stop.wait(0.14):
                        return
                    frame = capture()
                    if len(read_targets(frame, reader,
                                        lambda t: normalize(t) == "story")) == 1:
                        confirmed = True
                        break
                if confirmed:
                    break
            if stop.is_set():
                return
            if not confirmed:
                raise RuntimeError("Play did not open the Story menu.")
        log("Play menu opened.")

    log("Selecting Story.")
    if not select_text("Story", lambda t: normalize(t) == "story",
                       capture, reader, click, stop, timeout):
        return
    if stop.wait(0.10):
        return

    log(f"Finding map: {map_name}.")
    deadline = time.monotonic() + timeout
    focused = False
    missing_count = 0
    scroll_count = 0
    selected = False
    while not stop.is_set() and time.monotonic() < deadline:
        frame = capture()
        options = read_targets(frame, reader,
                               lambda t: normalize(t) == normalize(map_name))
        if stop.is_set():
            return
        if len(options) == 1:
            if not click_match(options[0], frame, click, stop):
                return
            selected = True
            break
        if not options and scroll is not None:
            missing_count += 1
            if missing_count >= 2:
                x = frame.shape[1] // 2
                y = min(frame.shape[0] - 1, round(frame.shape[0] * 0.86))
                if not focused:
                    if click(x, y, frame.shape) is False or stop.is_set():
                        return
                    focused = True
                if scroll_count >= max_map_scrolls:
                    raise RuntimeError(
                        f"Could not find {map_name} after {max_map_scrolls} downward map-list scrolls."
                    )
                scroll(MAP_SCROLL_STEPS, x, y, frame.shape)
                scroll_count += 1
                if stop.wait(MAP_SCROLL_SETTLE):
                    return
                continue
        if stop.wait(0.10):
            return
    if stop.is_set():
        return
    if not selected:
        raise RuntimeError(f"Could not uniquely identify map {map_name}.")

    if act is None:
        log("Story map selected. Ready for act selection.")
        return

    if stop.wait(0.10):
        return
    log(f"Selecting {act}.")
    if not select_text(act, lambda t: is_act_label(t, act),
                       capture, reader, click, stop, timeout):
        return
    if stop.wait(0.10):
        return

    if act not in ("Mastery", "Infinite"):
        if difficulty == "Hard":
            log("Selecting Hard difficulty.")
            if not select_text("Hard difficulty", lambda t: normalize(t) == "hard",
                               capture, reader, click, stop, timeout):
                return
            if stop.wait(0.14):
                return
        else:
            # Normal is already selected in-game; don't toggle difficulty.
            log("Normal difficulty (default).")

    log("Selecting stage.")
    if not select_text("Select Stage", lambda t: normalize(t) == "selectstage",
                       capture, reader, click, stop, timeout):
        return
    if stop.wait(0.10):
        return

    log("Starting Story.")
    if not select_text("Start", lambda t: normalize(t) == "start",
                       capture, reader, click, stop, timeout):
        return
    log("Start selected. Waiting for the game to load.")
