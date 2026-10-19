"""Serial unit indexing with fresh visual confirmation before each action."""
import re
import time

import cv2
import numpy as np

from python_macro.deployment import requested_wave
from python_macro.story import normalize
from python_macro.vision import Region

TARGETS = ("First", "Last", "Closest", "Strongest", "Boss", "Weakest",
           "Shielded", "Fastest", "Flying")


def priority_value(texts):
    values = {target for text in texts for target in TARGETS
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

    def read(self, frame):
        close = self.close_icon(frame)
        if close is None:
            return None
        x, y, w, h = close
        left, top = max(0, x-w*22), max(0, y-h)
        region = Region(left, top, min(frame.shape[1]-left, x+w-left),
                        min(frame.shape[0]-top, h*26))
        matches = self.reader.read(frame, region, scale=3, max_variants=2,
                                   min_confidence=0.75, cancelled=self.stop.is_set,
                                   accept=lambda found: priority_value([m.text for m in found]) is not None
                                   and upgrade_value([m.text for m in found]) is not None)
        texts = [m.text for m in matches]
        priority, upgrade = priority_value(texts), upgrade_value(texts)
        if priority is None and upgrade is None:
            return None
        return {"close": close[:2], "region": region, "priority": priority, "upgrade": upgrade}

    def auto_position(self, frame, panel):
        crop, (left, top) = panel["region"].crop(frame)
        found = self.auto_icon(crop)
        return (found[0]+left, found[1]+top) if found is not None else None


class UnitIndexer:
    def __init__(self, entries, client, capture, panel, stop, log, clock=time.monotonic):
        self.entries = entries
        self.client, self.capture, self.panel = client, capture, panel
        self.stop, self.log, self.clock = stop, log, clock
        self.completed = set()

    def wait(self, seconds):
        if self.stop.wait(seconds):
            raise InterruptedError()

    def snapshot(self):
        if self.stop.is_set():
            raise InterruptedError()
        frame = self.capture()
        panel = self.panel.read(frame)
        if self.stop.is_set():
            raise InterruptedError()
        return frame, panel

    def read_until(self, predicate, timeout=12):
        deadline = self.clock()+timeout
        while not self.stop.is_set() and self.clock() < deadline:
            frame, panel = self.snapshot()
            if panel is not None and predicate(panel):
                return frame, panel
            self.wait(0.15)
        if self.stop.is_set():
            raise InterruptedError()
        raise RuntimeError("Could not read the unit panel. Check the selected unit and try again.")

    def click(self, point, frame):
        if self.stop.is_set() or self.client.direct_click(*point, frame.shape) is False:
            raise InterruptedError()

    def key(self, value):
        if self.stop.is_set() or not self.client.hold_key(value, 0.15):
            raise InterruptedError()

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
        self.key(str(entry["unit"]))
        self.wait(0.25)
        self.click((int(entry["x"]), int(entry["y"])), frame)
        self.wait(0.35)
        frame, selected = self.snapshot()
        if selected is None:
            # Some placements do not open the panel automatically. Select the
            # saved position once; never re-send the slot key or repeat placement.
            self.click((int(entry["x"]), int(entry["y"])), frame)
        self.read_until(lambda panel: panel["priority"] is not None)
        for _ in range(18):
            _, panel = self.read_until(lambda panel: panel["priority"] is not None)
            if panel["priority"] == desired:
                break
            old = panel["priority"]
            self.key("R")
            self.wait(0.25)
            self.read_until(lambda panel: panel["priority"] not in (None, old))
        else:
            raise RuntimeError(f"Could not set target priority for Index {index+1}.")
        for _ in range(auto):
            self.read_until(lambda panel: panel["priority"] == desired)
            self.key("K")
            self.wait(0.2)
        if goal:
            last, stalled = None, self.clock()+120
            while not self.stop.is_set():
                _, panel = self.read_until(lambda panel: panel["upgrade"] is not None)
                value = panel["upgrade"]
                # Confirm a second read before declaring the upgrade complete.
                if value == "max" or value[0] >= goal or value[0] == value[1]:
                    self.wait(0.15)
                    _, confirm = self.read_until(lambda panel: panel["upgrade"] is not None)
                    final = confirm["upgrade"]
                    if final == "max" or (final[0] >= goal or final[0] == final[1]):
                        break
                    continue
                if value != last:
                    last, stalled = value, self.clock()+120
                if self.clock() >= stalled:
                    raise RuntimeError("Upgrade did not progress. Check available yen and the unit panel.")
                self.key("T")
                self.wait(0.45)
        if self.stop.is_set():
            raise InterruptedError()
        self.close()
        self.completed.add(index)
        self.log(f"Index {index+1} complete.")

    def close(self):
        for _ in range(3):
            frame, panel = self.snapshot()
            if panel is None:
                self.wait(0.15)
                if self.panel.close_icon(self.capture()) is None:
                    return
                continue
            self.click(panel["close"], frame)
            self.wait(0.2)
        if self.panel.close_icon(self.capture()) is not None:
            raise RuntimeError("Could not close the unit panel.")
