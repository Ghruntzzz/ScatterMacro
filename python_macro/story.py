"""Cancellable Anime Expeditions Story navigation with the verified mouse method.

Play -> Story -> Map -> Act -> Difficulty (Acts 1-5) -> Select Stage -> Start.
The live worker supplies the dashboard's saved act and difficulty settings.
"""
import re
import time

from python_macro.vision import Region

MAX_MAP_SCROLLS = 12
MAP_SCROLL_STEPS = -4
MAP_SCROLL_SETTLE = 0.04


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


def read_targets(frame, reader, predicate, *, thorough=True, stop=None):
    matches = reader.read(
        frame, Region(0, 0, frame.shape[1], frame.shape[0]),
        scale=2 if thorough else 1, min_confidence=0.65,
        max_variants=3 if thorough else 1,
        cancelled=stop.is_set if stop is not None else None,
        accept=lambda found: sum(predicate(match.text) for match in found) == 1,
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
    scans = 0
    while not stop.is_set() and time.monotonic() < deadline:
        frame = capture()
        options = read_targets(frame, reader, predicate, thorough=scans % 3 == 2, stop=stop)
        scans += 1
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
                   skip_play=False, act_name=None, difficulty="Normal", find_act=None,
                   find_start=None, verify_clicks=False, highlight=None):
    """Navigate using captured Roblox client coordinates and cancellable input.

    act_name=None retains the legacy map-only contract for existing callers;
    the live Story worker always supplies the selected dashboard act.
    """
    if verify_clicks:
        from python_macro.story_verified import navigate_story_checked
        return navigate_story_checked(
            map_name, capture, reader, click, stop, log, timeout=timeout,
            scroll=scroll, max_map_scrolls=max_map_scrolls,
            find_play=find_play, skip_play=skip_play, act_name=act_name,
            difficulty=difficulty, find_act=find_act, find_start=find_start,
            highlight=highlight,
        )
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
            while not stop.is_set() and time.monotonic() < deadline:
                frame = capture()
                location = find_play(frame)
                if location is not None:
                    if click(int(location[0]), int(location[1]), frame.shape) is False:
                        return
                    break
                if stop.wait(0.12):
                    return
            else:
                if not stop.is_set():
                    raise RuntimeError("Could not find Play button image.")
                return
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
                               lambda t: normalize(t) == normalize(map_name), stop=stop)
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
    selected_act = False
    if find_act is not None:
        deadline = time.monotonic() + timeout
        while not stop.is_set() and time.monotonic() < deadline:
            frame = capture()
            target = find_act(frame, act)
            if target is not None:
                selected_act = click(int(target[0]), int(target[1]), frame.shape) is not False
                break
            if stop.wait(0.10):
                return
    else:
        selected_act = select_text(act, lambda t: is_act_label(t, act),
                                   capture, reader, click, stop, timeout)
    if not selected_act or stop.is_set():
        if stop.is_set():
            return
        raise RuntimeError(f"Could not identify {act} button. No other act was clicked.")
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
            log("Normal difficulty.")

    log("Selecting stage.")
    if not select_text("Select Stage", lambda t: normalize(t) == "selectstage",
                       capture, reader, click, stop, timeout):
        return
    if stop.wait(0.10):
        return

    log("Starting Story.")
    if find_start is None:
        if not select_text("Start", lambda t: normalize(t) == "start",
                           capture, reader, click, stop, timeout):
            return
    else:
        deadline = time.monotonic() + timeout
        while not stop.is_set() and time.monotonic() < deadline:
            frame = capture()
            target = find_start(frame)
            if target is not None:
                x, y = int(target[0]), int(target[1])
                log(f"Start button image found at ({x}, {y}); score {target[2]:.2f}.")
                if click(x, y, frame.shape) is False:
                    return
                break
            if stop.wait(0.08):
                return
        else:
            if not stop.is_set():
                raise RuntimeError("Could not locate Start button image.")
            return
    log("Start selected. Waiting for the game to load.")
