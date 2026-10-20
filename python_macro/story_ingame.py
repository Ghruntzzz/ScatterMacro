"""Story in-game flow, separate from lobby navigation. No blind placement."""
import re
import time

import cv2

from python_macro.unit_actions import UnitIndexer, UnitPanel
from python_macro.story import normalize
from python_macro.vision import Region, StartButtonLocator
from python_macro.end_screen import EndScreenReader, save_rewards
from python_macro.match_monitor import MatchMonitor


class RoundEnded(Exception):
    pass


def already_in_match(capture, reader, stop, map_name, act, difficulty, find_play=None,
                     mode='Story', wait_seconds=3):
    confirmed = 0
    deadline = time.monotonic()+wait_seconds
    while not stop.is_set():
        if stop.is_set():
            return False
        frame = capture()
        h, w = frame.shape[:2]
        matches = reader.read(frame, Region(w//2, 0, w-w//2, h),
                              scale=2, max_variants=2, min_confidence=.7,
                              cancelled=stop.is_set)
        texts = [m.text for m in matches]
        if not matches_story(texts, map_name, act, difficulty, mode=mode):
            text = normalize(" ".join(texts))
            if re.search(r"act[1-9]", text) and (
                    ('story' in text and ('normalmod' in text or 'hardmod' in text)) or 'raid' in text):
                raise RuntimeError(f"Already in a different {mode} match. Select its mode, map and act in the dashboard.")
            confirmed = 0
        else:
            confirmed += 1
            if confirmed >= 2:
                return True
        remaining = deadline-time.monotonic()
        if remaining <= 0 or stop.wait(min(.1,remaining)):
            break
    return False


def matches_story(texts, map_name, act, difficulty, mode='Story'):
    text = normalize(" ".join(texts))
    if normalize(mode) not in text or normalize(map_name) not in text:
        return False
    difficulty_label = normalize(difficulty) + "mod"
    if mode == 'Story' and not any(normalize(line) in (difficulty_label, difficulty_label + "e") for line in texts):
        return False
    if act.startswith("Act "):
        return re.search(r"act" + re.escape(act[-1]) + r"(?![0-9])", text) is not None
    return normalize(act) in text


def parse_wave(texts):
    values = set()
    for text in texts:
        match = re.search(r"(?<!\d)(\d{1,3})\s*/\s*(\d{1,3})(?!\d)", text)
        if match:
            current, total = map(int, match.groups())
            if 1 <= total <= 999 and 0 <= current <= total:
                values.add((current, total))
    return next(iter(values)) if len(values) == 1 else None


def parse_yen(texts):
    values = set()
    for text in texts:
        text = text.strip().replace(",", "").replace("¥", "").strip()
        if re.fullmatch(r"\d{1,9}", text):
            values.add(int(text))
    return next(iter(values)) if len(values) == 1 else None


class HudReader:
    def __init__(self, reader, stop, assets):
        self.reader, self.stop = reader, stop
        reference = cv2.imread(str(assets / "yen-template.png"), cv2.IMREAD_GRAYSCALE)
        if reference is None:
            raise RuntimeError("Yen reference image is missing.")
        # Use only the currency icon, never the sample balance of 600.
        icon = reference[:, :30]
        self.yen_tiles = [cv2.resize(icon, None, fx=s, fy=s)
                          for s in (0.8, 1, 1.25, 1.5, 2)]
        self.wave_region = None
        self.scans = 0

    def read(self, frame, region, scale=2):
        return self.reader.read(frame, region, scale=scale, max_variants=1,
                                min_confidence=0.75, cancelled=self.stop.is_set)

    def wave(self, frame):
        self.scans += 1
        if self.wave_region is not None:
            try:
                value = parse_wave([m.text for m in self.read(frame, self.wave_region)])
                if value is not None:
                    return value
            except ValueError:
                pass
            self.wave_region = None
        height, width = frame.shape[:2]
        region = Region(0, 0, width, height if self.scans % 3 == 0 else max(1, height // 2))
        matches = self.read(frame, region, scale=1)
        # Anchor to the word "wave" to avoid confusing other progress fractions.
        anchors = [m for m in matches if normalize(m.text).endswith("wave")]
        if len(anchors) != 1:
            return None
        anchor = anchors[0]
        xs, ys = zip(*anchor.corners)
        h = max(12, round(max(ys) - min(ys)))
        left, top = max(0, round(min(xs)) - h * 8), max(0, round(min(ys)) - h)
        self.wave_region = Region(left, top, min(width - left, round(max(xs)) - left + h),
                                  min(height - top, h * 3))
        return parse_wave([m.text for m in self.read(frame, self.wave_region)])

    def yen(self, frame):
        gray = cv2.cvtColor(frame[:, :, :3], cv2.COLOR_BGR2GRAY)
        # Currency is in the lower HUD. Never interpret unit prices as balance.
        top = frame.shape[0] // 2
        roi = gray[top:]
        best = None
        for tile in self.yen_tiles:
            h, w = tile.shape
            if h > roi.shape[0] or w > roi.shape[1]:
                continue
            _, score, _, p = cv2.minMaxLoc(cv2.matchTemplate(roi, tile, cv2.TM_CCOEFF_NORMED))
            if best is None or score > best[0]:
                best = score, p, w, h
        if best is None or best[0] < 0.9:
            return None
        _, (x, y), w, h = best
        x += w
        if x >= frame.shape[1]:
            return None
        region = Region(x, top + y, min(w * 5, frame.shape[1] - x), h)
        return parse_yen([m.text for m in self.read(frame, region)])


def run_story_ingame(map_name, act, difficulty, capture, client, reader, stop,
                     log, assets, entries=(), status=lambda value: None,
                     monitor_capture=None, reward_dir=None, entries_provider=None,
                     match_confirmed=False, on_result=lambda *args: None, mode='Story'):
    log("Waiting for match details.")
    confirmed = 0
    scans = 0
    while not match_confirmed and not stop.is_set():
        frame = capture()
        h, w = frame.shape[:2]
        scans += 1
        matches = reader.read(frame, Region(w // 2, 0, w - w // 2, h),
                              scale=2 if scans % 3 == 0 else 1, max_variants=1,
                              min_confidence=0.75, cancelled=stop.is_set)
        if not matches_story([m.text for m in matches], map_name, act, difficulty, mode=mode):
            anchors = [m for m in matches if normalize(m.text).startswith(normalize(mode))]
            if len(anchors) == 1:
                xs, ys = zip(*anchors[0].corners)
                left = max(w // 2, round(min(xs)) - 25)
                top = max(0, round(min(ys)) - 15)
                label_height = max(12, round(max(ys) - min(ys)))
                matches = reader.read(frame, Region(left, top, w - left,
                                      min(h - top, label_height * 6)),
                                      scale=3, max_variants=3, min_confidence=0.75,
                                      cancelled=stop.is_set,
                                      accept=lambda found: matches_story(
                                          [m.text for m in found], map_name, act, difficulty, mode=mode))
        confirmed = confirmed + 1 if matches_story([m.text for m in matches], map_name, act, difficulty, mode=mode) else 0
        if confirmed >= 2:
            break
        if stop.wait(0.25):
            return
    if stop.is_set():
        return
    log("Match found. Setting up camera.")
    if not client.setup_camera() or stop.is_set():
        return
    log("Camera ready. Starting game.")
    run_matches(capture, client, reader, stop, log, assets, entries, status,
                monitor_capture or capture, reward_dir, entries_provider, allow_active=match_confirmed,
                on_result=on_result)


def start_game(capture, client, stop, assets, active_hud=None):
    find_start = StartButtonLocator(assets / "start-game-template.png")
    # Wait through loading indefinitely; retries are fresh detections, and
    # disappearing for two captures confirms that the button was dismissed.
    clicked, absent = False, 0
    previous_wave = None
    while not stop.is_set():
        frame = capture()
        target = find_start(frame)
        if stop.is_set():
            return
        if target is not None:
            absent = 0
            if client.start_click(int(target[0]), int(target[1]), frame.shape) is False:
                return
            clicked = True
            if stop.wait(0.6):
                return
        elif clicked:
            absent += 1
            if absent >= 2:
                return True
        elif active_hud is not None:
            wave = active_hud.wave(frame)
            if wave is not None and wave == previous_wave and wave[0] > 0:
                return True
            previous_wave = wave
        if stop.wait(0.15):
            return
    return False


def finish_match(capture, client, reader, stop, log, status, reward_dir, started, find_start,
                 on_result=lambda *args: None):
    end = EndScreenReader(reader, stop)
    previous, counted = None, False
    reward_logged = False
    clicked_repeat = False
    while not stop.is_set():
        frame = capture()
        if clicked_repeat and find_start(frame) is not None:
            return True
        reading = end.read(frame)
        if stop.is_set():
            return False
        outcome = reading["outcome"]
        if outcome and outcome == previous:
            if not counted:
                counted = True
                log(f"{outcome.title()} detected.")
                duration = time.monotonic()-started
                status({"result": outcome, "duration": duration})
                saved = None
                if reward_dir is not None:
                    try:
                        saved = save_rewards(frame, end.rewards(frame, reading), reward_dir)
                    except OSError:
                        log("Could not save reward images.")
                on_result(outcome, duration, saved)
                # Network delivery may take seconds: locate Repeat again in
                # a fresh capture rather than clicking stale coordinates.
                previous = outcome
                continue
            if reading["repeat"] is not None:
                if not clicked_repeat:
                    log("Repeating stage.")
                if client.direct_click(*reading["repeat"], frame.shape) is False:
                    return False
                clicked_repeat = True
                if stop.wait(.5):
                    return False
        elif reading["reward"] and not counted:
            if not reward_logged:
                log("Collecting rewards.")
                reward_logged = True
            # The counter is current/total, so include the final close click.
            # Batch only the validated remaining pages, then rescan for misses.
            for _ in range(reading.get('reward_clicks',1)):
                if stop.is_set():
                    return False
                if client.direct_click(frame.shape[1]//2, int(frame.shape[0]*.12), frame.shape) is False:
                    return False
                if stop.wait(.12):
                    return False
        previous = outcome
        if stop.wait(.1):
            return False
    return False


def run_matches(capture, client, reader, stop, log, assets, entries, status,
                monitor_capture, reward_dir, entries_provider=None, allow_active=False,
                on_result=lambda *args: None):
    monitor = MatchMonitor(monitor_capture, assets, status)
    monitor.start()
    try:
        while not stop.is_set():
            active_hud = HudReader(reader, stop, assets) if allow_active else None
            if not start_game(capture, client, stop, assets, active_hud):
                return
            allow_active = False
            started = time.monotonic()
            log("Game started.")
            status({"wave": None, "yen": None, "eligible_indexes": [], "new_run": True})
            monitor.reset()
            def checkpoint():
                state = monitor.snapshot()
                if state.get("error"):
                    raise RuntimeError("Screen monitoring failed: " + state["error"])
                if state["outcome"] or state["reward"]:
                    raise RoundEnded()
                return state["wave"]
            indexer = UnitIndexer(entries_provider() if entries_provider else entries,
                                  client, capture, UnitPanel(reader, stop, assets),
                                  stop, log, heartbeat=checkpoint)
            waiting_logged = False
            try:
                while not stop.is_set():
                    wave = checkpoint()
                    indexer.check_abilities(wave[0] if wave else None)
                    next_index = indexer.next_ready(wave[0] if wave else None)
                    if next_index is not None:
                        indexer.run(next_index)
                    elif not waiting_logged and indexer.all_done():
                        log("Unit setup complete. Waiting for game end.")
                        waiting_logged = True
                    if stop.wait(.1):
                        return
            except RoundEnded:
                pass
            if stop.is_set() or not finish_match(capture, client, reader, stop, log,
                                                status, reward_dir, started,
                                                StartButtonLocator(assets / "start-game-template.png"),
                                                on_result=on_result):
                return
    finally:
        monitor.close()
