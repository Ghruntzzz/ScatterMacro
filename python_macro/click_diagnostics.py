"""Controlled Play click-method diagnostics.

Only sends foreground mouse input to the single Roblox HWND. Each method is
followed by OCR verification that Story is available; stop after first success.
"""
import time

from python_macro.story import normalize
from python_macro.vision import Region

PLAY_METHODS = (
    ("SendInput direct", "direct_click"),
    ("mouse_event direct", "direct_click_event"),
    ("SendInput absolute", "direct_click_absolute"),
    ("WM_LBUTTON messages", "direct_click_message"),
)


def story_visible(frame, reader):
    matches = reader.read(
        frame, Region(0, 0, frame.shape[1], frame.shape[0]),
        scale=1, min_confidence=0.8,
        accept=lambda items: any(normalize(m.text) == "story" for m in items),
    )
    return sum(normalize(m.text) == "story" for m in matches) == 1


def test_play_methods(client, find_play, reader, stop, log, timeout=30,
                      methods=PLAY_METHODS):
    """Try each click method once, verify UI, return its name or raise.

    A method returning True means Windows sent the input, not that Roblox
    accepted it. The Story screen is the only confirmation.
    """
    deadline = time.monotonic() + timeout
    failed = []
    for label, method_name in methods:
        if stop.is_set():
            return None
        if time.monotonic() >= deadline:
            break
        log(f"Testing {label}.")
        try:
            if not client.focus_roblox():
                return None
            frame = client.capture()
            # The menu may already have opened between attempts.
            if story_visible(frame, reader):
                log("Story is already visible. No more clicks needed.")
                return label
            position = find_play(frame)
            if position is None:
                raise RuntimeError("Play icon not found on the current Roblox frame.")
            x, y = int(position[0]), int(position[1])
            log(f"Play icon at client ({x}, {y}), match confidence {position[2]:.2f}.")
            sent = getattr(client, method_name)(x, y, frame.shape)
            if stop.is_set():
                return None
            if not sent:
                log(f"{label}: input cancelled.")
                return None
            log(f"{label}: input sent. Checking for Story menu.")
            for _ in range(6):
                if stop.wait(0.25):
                    return None
                if not client.focus_roblox():
                    return None
                if story_visible(client.capture(), reader):
                    log(f"SUCCESS: {label} opened the Story menu. Stopping method tests.")
                    return label
            failed.append(label)
            log(f"NO MENU CHANGE: {label}. Trying next method.")
        except RuntimeError as error:
            # Focus failures must stop all further methods, never click a
            # different foreground window.
            if "focus" in str(error).lower() or "foreground" in str(error).lower():
                raise
            failed.append(label)
            log(f"{label} failed: {error}")
    if stop.is_set():
        return None
    raise RuntimeError(
        "None of the Play click methods was verified. Tried: " +
        ", ".join(failed or [name for name, _ in methods]) +
        ". Check Action Output; Windows accepting input does not prove Roblox received it."
    )
