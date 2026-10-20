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
    def __init__(self, path, threshold=0.92, scales=None):
        source = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if source is None:
            raise RuntimeError("Unit button reference image is missing.")
        self.tiles = [cv2.resize(source, None, fx=s, fy=s)
                      for s in (scales if scales is not None else (0.8, 1, 1.25, 1.5, 1.75, 2))]
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


class AbilitySwitch:
    """Match only the pill interior, excluding the variable game background."""
    def __init__(self, assets):
        self.tiles = []
        for state in ('off','on'):
            source = cv2.imread(str(assets / f'unit-ability-{state}.png'))
            if source is None:
                raise RuntimeError('Auto Ability reference image is missing.')
            h,w = source.shape[:2]
            mask = np.zeros((h,w),np.uint8)
            radius = max(2,(w-8)//2)
            cx = w//2
            cv2.rectangle(mask,(cx-radius,3+radius),(cx+radius,h-4-radius),255,-1)
            cv2.circle(mask,(cx,3+radius),radius,255,-1)
            cv2.circle(mask,(cx,h-4-radius),radius,255,-1)
            for scale in np.arange(.6,2.05,.05):
                tile = cv2.resize(source,None,fx=scale,fy=scale)
                scaled_mask = cv2.resize(mask,(tile.shape[1],tile.shape[0]),interpolation=cv2.INTER_NEAREST)
                hsv = cv2.cvtColor(tile,cv2.COLOR_BGR2HSV)
                color = self.color_mask(hsv,state) & (scaled_mask > 0)
                ys,xs = np.nonzero(color)
                self.tiles.append((state,tile,scaled_mask,float(xs.mean()),float(ys.mean())))

    @staticmethod
    def color_mask(hsv,state):
        hue = hsv[:,:,0]
        color = ((hue < 12) | (hue > 170)) if state == 'off' else ((hue > 30) & (hue < 90))
        return color & (hsv[:,:,1] > 120) & (hsv[:,:,2] > 120)

    def __call__(self, frame):
        frame = np.ascontiguousarray(frame[:,:,:3])
        hits = []
        hsv_frame = cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        candidates = {}
        for state in ('off','on'):
            binary = self.color_mask(hsv_frame,state).astype(np.uint8)*255
            contours,_ = cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            candidates[state] = [cv2.boundingRect(c) for c in contours
                                 if cv2.contourArea(c) >= 20]
        for state,tile,mask,kx,ky in self.tiles:
            h,w = tile.shape[:2]
            for bx,by,bw,bh in candidates[state]:
                if not (.4*w <= bw <= w and .3*w <= bh <= 1.2*w):
                    continue
                x0,y0 = round(bx+bw/2-kx),round(by+bh/2-ky)
                left,top = max(0,x0-4),max(0,y0-4)
                crop = frame[top:y0+h+5,left:x0+w+5]
                if crop.shape[0] < h or crop.shape[1] < w:
                    continue
                scores = cv2.matchTemplate(crop,tile,cv2.TM_SQDIFF_NORMED,mask=mask)
                scores = np.nan_to_num(scores,nan=1,posinf=1,neginf=1)
                score,_,point,_ = cv2.minMaxLoc(scores)
                if score <= .20:
                    x,y = point
                    hits.append((score,state,(left+x+round(kx),top+y+round(ky))))
        if not hits:
            return None
        _,state,point = min(hits,key=lambda hit:hit[0])
        return state,point


class UnitPanel:
    def __init__(self, reader, stop, assets):
        self.reader, self.stop = reader, stop
        self.close_icon = Icon(assets / "unit-close.png")
        self.auto_icon = Icon(assets / "unit-auto-upgrade.png")
        self.ability_switch = AbilitySwitch(assets)

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
        found = self.ability_state(frame)
        return found[1] if found is not None and found[0] == 'off' else None

    def ability_state(self, frame):
        close = self.close_icon(frame)
        if close is None:
            return None
        x, y, w, h = close
        left, top = max(0, x-14*w), max(0, y-h)
        crop = frame[top:min(frame.shape[0], y+16*h), left:min(frame.shape[1], x+3*w)]
        found = self.ability_switch(crop)
        if found is None:
            return None
        state,(cx,cy) = found
        return state,(cx+left,cy+top)


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
                    if self.enable_ability():
                        self.ability_checked.add(index)
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

    def enable_ability(self):
        """Only click the red/off switch, confirming panel presence each time."""
        absent = 0
        clicked = False
        for _ in range(6):
            self.heartbeat()
            if self.stop.is_set():
                raise InterruptedError()
            frame = self.capture()
            if self.panel.close_icon(frame) is None:
                return False
            found = self.panel.ability_state(frame)
            if found is None:
                absent += 1
                if absent >= 2 and not clicked:
                    return True
                self.wait(.1)
            elif found[0] == 'on':
                return True
            else:
                absent = 0
                self.click(found[1], frame)
                clicked = True
                self.wait(.3)
        self.log('Auto Ability could not be confirmed on.')
        return False

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
        try:
            self.enable_ability()
        finally:
            if not self.stop.is_set():
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
