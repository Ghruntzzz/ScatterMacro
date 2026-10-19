"""Serial unit indexing with fresh visual confirmation before each action."""
import re
import time

import cv2
import numpy as np

from python_macro.deployment import requested_wave
from python_macro.story import normalize
from python_macro.vision import Region
from python_macro.upgrade_bars import read_upgrade_bars

TARGETS = ("First", "Last", "Closest", "Strongest", "Boss", "Weakest",
           "Shielded", "Fastest", "Flying")


def priority_value(texts):
    values = {target for text in texts for target in (*TARGETS, "None")
              if normalize(text) in (normalize(target), "priority" + normalize(target))}
    return next(iter(values)) if len(values) == 1 else None


def upgrade_value(texts):
    values = set()
    for text in texts:
        if normalize(text) in ("max", "maxed", "upgrademax", "upgrademaxed"):
            return "max"
        match = re.search(r"upgrade\s*(\d{1,2})\s*/\s*(\d{1,2})(?!\d)", text, re.I)
        if match:
            level, maximum = map(int, match.groups())
            if 0 <= level <= maximum <= 99 and maximum > 0:
                values.add((level, maximum))
    return next(iter(values)) if len(values) == 1 else None


class Icon:
    def __init__(self, path, threshold=0.92):
        source = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if source is None:
            raise RuntimeError("Unit button reference image is missing.")
        self.tiles = [cv2.resize(source, None, fx=s, fy=s)
                      for s in (0.8, 1, 1.25, 1.5, 1.75, 2)]
        self.threshold = threshold

    def __call__(self, frame):
        gray = cv2.cvtColor(np.ascontiguousarray(frame[:, :, :3]), cv2.COLOR_BGR2GRAY)
        hits = []
        for tile in self.tiles:
            h, w = tile.shape
            if h > gray.shape[0] or w > gray.shape[1]:
                continue
            scores = cv2.matchTemplate(gray, tile, cv2.TM_CCOEFF_NORMED)
            for _ in range(2):
                _, score, _, p = cv2.minMaxLoc(scores)
                if score < self.threshold:
                    break
                hits.append((score, p[0]+w//2, p[1]+h//2, w, h))
                scores[max(0,p[1]-h):p[1]+h, max(0,p[0]-w):p[0]+w] = -1
        if not hits:
            return None
        best = max(hits)
        if any(abs(hit[1]-best[1]) > best[3] or abs(hit[2]-best[2]) > best[4] for hit in hits):
            return None
        return best[1:]


class UnitPanel:
    def __init__(self, reader, stop, assets):
        self.reader, self.stop = reader, stop
        self.close_icon = Icon(assets / "unit-close.png")
        self.auto_icon = Icon(assets / "unit-auto-upgrade.png")
        self.ability_icon = Icon(assets / "unit-ability-off.png", threshold=.90)

    def read(self, frame, need_upgrade=False):
        close = self.close_icon(frame)
        if close is None:
            return None
        x, y, w, h = close
        left, top = max(0, x-w*14), max(0, y-h)
        region = Region(left, top, min(frame.shape[1]-left, x+w-left),
                        min(frame.shape[0]-top, h*11))
        if need_upgrade:
            upgrade = read_upgrade_bars(frame, close)
            if upgrade is None:
                return None
            return {"close": close[:2], "region": region, "priority": None, "upgrade": upgrade}
        priority_region = Region(max(0, x-13*w), max(0, y+6*h), 4*w, 3*h)
        matches = self.reader.read(frame, priority_region, scale=3, max_variants=1,
                                   min_confidence=0.75, cancelled=self.stop.is_set)
        priority = priority_value([m.text for m in matches])
        upgrade = None
        if priority is None:
            matches = self.reader.read(frame, region, scale=3, max_variants=2,
                                   min_confidence=0.75, cancelled=self.stop.is_set,
                                   accept=lambda found: priority_value([m.text for m in found]) is not None)
            priority = priority_value([m.text for m in matches])
        if priority is None and upgrade is None:
            return None
        return {"close": close[:2], "region": region, "priority": priority, "upgrade": upgrade}

    def auto_position(self, frame, panel):
        crop, (left, top) = panel["region"].crop(frame)
        found = self.auto_icon(crop)
        return (found[0]+left, found[1]+top) if found is not None else None

    def ability_position(self, frame):
        close = self.close_icon(frame)
        if close is None:
            return None
        x, y, w, h = close
        left, top = max(0, x-14*w), max(0, y-h)
        crop = frame[top:min(frame.shape[0], y+11*h), left:min(frame.shape[1], x+w)]
        found = self.ability_icon(crop)
        if found is None:
            return None
        cx, cy, tw, th = found
        # Only the red/off state is clickable. Grayscale matching alone could
        # also match the enabled switch and inadvertently turn it off.
        tile = crop[max(0,cy-th//2):cy+th//2, max(0,cx-tw//2):cx+tw//2, :3]
        hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
        red = ((hsv[:,:,0] < 12) | (hsv[:,:,0] > 170)) & (hsv[:,:,1] > 120) & (hsv[:,:,2] > 120)
        if np.mean(red) < .08:
            return None
        return cx+left, cy+top


class UnitIndexer:
    def __init__(self, entries, client, capture, panel, stop, log, clock=time.monotonic,
                 heartbeat=lambda: None):
        self.entries = entries
        self.client, self.capture, self.panel = client, capture, panel
        self.stop, self.log = stop, log
        def active_clock():
            paused = getattr(client, 'focus_pause_time', 0.0)
            return clock() - (paused if isinstance(paused, (float,int)) else 0.0)
        self.clock = active_clock
        self.completed = set()
        self.heartbeat = heartbeat
        self.placed = {}
        self.ability_checked = set()
        self.active_index = None
        self.checking_ability = False

    def checkpoint(self):
        wave = self.heartbeat()
        if not self.checking_ability:
            self.check_abilities(wave[0] if wave else None)

    def wait(self, seconds):
        if self.stop.wait(seconds):
            raise InterruptedError()

    def snapshot(self, need_upgrade=False):
        if self.stop.is_set():
            raise InterruptedError()
        self.checkpoint()
        frame = self.capture()
        panel = self.panel.read(frame, need_upgrade=True) if need_upgrade else self.panel.read(frame)
        if self.stop.is_set():
            raise InterruptedError()
        return frame, panel

    def read_until(self, predicate, timeout=12, need_upgrade=False):
        deadline = self.clock()+timeout
        while not self.stop.is_set() and self.clock() < deadline:
            frame, panel = self.snapshot(need_upgrade=True) if need_upgrade else self.snapshot()
            if panel is not None and predicate(panel):
                return frame, panel
            self.wait(0.15)
        if self.stop.is_set():
            raise InterruptedError()
        raise RuntimeError("Could not read the unit panel. Check the selected unit and try again.")

    def click(self, point, frame):
        self.heartbeat()
        if self.stop.is_set() or self.client.direct_click(*point, frame.shape) is False:
            raise InterruptedError()

    def key(self, value):
        self.heartbeat()
        if self.stop.is_set() or not self.client.hold_key(value, 0.10):
            raise InterruptedError()

    def all_done(self):
        return all(i in self.completed or str(e.get("unit", "0")) not in {"1","2","3","4","5","6"}
                   for i, e in enumerate(self.entries))

    def check_abilities(self, wave):
        if wave is None or self.checking_ability:
            return
        self.checking_ability = True
        try:
            for index, point in list(self.placed.items()):
                required = requested_wave(self.entries[index].get("auto_ability_wave", ""))
                if required is None or wave < required or index in self.ability_checked:
                    continue
                restore = self.placed.get(self.active_index)
                try:
                    self.close()
                    self.click(point, self.capture())
                    self.wait(.15)
                    # Confirm the panel before concluding it has no ability.
                    for _ in range(8):
                        frame = self.capture()
                        if self.panel.close_icon(frame) is not None:
                            break
                        self.wait(.15)
                    else:
                        continue
                    for _ in range(3):
                        frame = self.capture()
                        ability = self.panel.ability_position(frame)
                        if ability is None:
                            self.wait(.1)
                            if self.panel.ability_position(self.capture()) is None:
                                self.ability_checked.add(index)
                                break
                        else:
                            self.click(ability, frame)
                            self.wait(.2)
                finally:
                    if not self.stop.is_set():
                        self.heartbeat()
                        self.close()
                        if restore is not None:
                            self.click(restore, self.capture())
                            self.wait(.15)
        finally:
            self.checking_ability = False

    def next_ready(self, wave):
        # Strict numerical order: an earlier configured wave blocks later indexes.
        for index, entry in enumerate(self.entries):
            if index in self.completed or str(entry.get("unit", "0")) not in {"1","2","3","4","5","6"}:
                continue
            if not all(str(entry.get(key, "")).isdecimal() for key in ("x", "y")):
                raise RuntimeError(f"Set the position for Index {index+1} before starting.")
            required = requested_wave(entry.get("place_at_wave", ""))
            return index if required is None or (wave is not None and wave >= required) else None
        return None

    def placement_panel(self, frame, panel):
        if panel is not None:
            return panel
        # A visible close button means the panel opened even if its priority
        # is unreadable. Never repeat placement just because OCR failed.
        close = self.panel.close_icon(frame)
        if close is not None:
            return {"close": close[:2], "priority": None, "upgrade": None}
        return None

    def place(self, index, entry):
        x, y = int(entry["x"]), int(entry["y"])
        points = [(x,y)]*3 + [(x+6,y),(x-6,y),(x,y+6),(x,y-6)]
        for attempt, point in enumerate(points):
            if self.stop.is_set():
                raise InterruptedError()
            frame = self.capture()
            if attempt:
                frame, panel = self.snapshot()
                panel = self.placement_panel(frame, panel)
                if panel is not None:
                    return panel
            if not (0 <= point[0] < frame.shape[1] and 0 <= point[1] < frame.shape[0]):
                if attempt == 0:
                    raise RuntimeError(f"Index {index+1} position is outside Roblox.")
                continue
            self.key(str(entry["unit"]))
            self.wait(0.15)
            self.last_place_point = point
            self.click(point, frame)
            for scan in range(4):
                self.wait(0.12)
                frame, panel = self.snapshot()
                panel = self.placement_panel(frame, panel)
                if panel is not None:
                    return panel
                if scan == 1:
                    # Select a successfully placed unit whose panel didn't
                    # open automatically, before attempting another placement.
                    self.click(point, frame)
        raise RuntimeError(f"Could not confirm placement for Index {index+1}. Check the position and available yen.")

    def run(self, index):
        entry = self.entries[index]
        desired = entry.get("priority", "First")
        auto, goal = int(entry.get("auto_upgrade", "0")), int(entry.get("upgrade", "0"))
        if desired not in TARGETS or not 0 <= auto <= 6 or not 0 <= goal <= 15:
            raise RuntimeError(f"Check the settings for Index {index+1}.")
        self.log(f"Placing Index {index+1}.")
        frame, existing = self.snapshot()
        if existing is not None:
            self.close()
            frame = self.capture()
        panel = self.place(index, entry)
        self.placed[index] = getattr(self, "last_place_point", (int(entry["x"]), int(entry["y"])))
        self.active_index = index
        for _ in range(18):
            if self.stop.is_set():
                raise InterruptedError()
            if panel is None or panel["priority"] is None:
                _, panel = self.read_until(lambda panel: panel["priority"] is not None)
            if panel["priority"] == "None":
                # Non-targeting units have no priority to cycle. Confirm this
                # is a real label, not a transient OCR miss (Python None).
                self.wait(0.15)
                _, confirmed = self.read_until(lambda panel: panel["priority"] is not None)
                if confirmed["priority"] == "None":
                    break
                panel = confirmed
                continue
            if panel["priority"] == desired:
                break
            old = panel["priority"]
            self.key("R")
            self.wait(0.12)
            _, panel = self.read_until(lambda panel: panel["priority"] not in (None, old))
        else:
            raise RuntimeError(f"Could not set target priority for Index {index+1}.")
        for _ in range(auto):
            self.key("K")
            self.wait(0.1)
        if goal:
            last, stalled = None, self.clock()+120
            while not self.stop.is_set():
                _, panel = self.read_until(lambda panel: panel["upgrade"] is not None, need_upgrade=True)
                value = panel["upgrade"]
                # Confirm a second read before declaring the upgrade complete.
                if value == "max" or value[0] >= goal or value[0] == value[1]:
                    self.wait(0.15)
                    _, confirm = self.read_until(lambda panel: panel["upgrade"] is not None, need_upgrade=True)
                    final = confirm["upgrade"]
                    if final == "max" or (final[0] >= goal or final[0] == final[1]):
                        break
                    continue
                if value != last:
                    last, stalled = value, self.clock()+120
                if self.clock() >= stalled:
                    raise RuntimeError("Upgrade did not progress. Check available yen and the unit panel.")
                self.key("T")
                self.wait(0.2)
        if self.stop.is_set():
            raise InterruptedError()
        self.close()
        self.completed.add(index)
        self.active_index = None
        self.log(f"Index {index+1} complete.")

    def close(self):
        for _ in range(3):
            if self.stop.is_set():
                raise InterruptedError()
            frame = self.capture()
            point = self.panel.close_icon(frame)
            if point is None:
                self.wait(0.15)
                if self.panel.close_icon(self.capture()) is None:
                    return
                continue
            self.click(point[:2], frame)
            self.wait(0.2)
        if self.panel.close_icon(self.capture()) is not None:
            raise RuntimeError("Could not close the unit panel.")
