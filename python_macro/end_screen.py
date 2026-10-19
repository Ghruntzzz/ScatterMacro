"""OCR end-screen recognition and local reward evidence for future webhooks."""
import json
from pathlib import Path

import cv2

from python_macro.story import normalize
from python_macro.vision import Region


def center(match):
    xs, ys = zip(*match.corners)
    return round((min(xs)+max(xs))/2), round((min(ys)+max(ys))/2)


def interpret_end(top, bottom):
    labels = {normalize(m.text) for m in top}
    all_text = normalize(" ".join(m.text for m in (*top, *bottom)))
    outcomes = labels.intersection({"victory", "defeat"})
    repeat = [m for m in bottom if normalize(m.text) == "repeatstage"]
    outcome = next(iter(outcomes)) if len(outcomes) == 1 and (
        "gainedrewards" in all_text or "gamestats" in all_text or len(repeat) == 1) else None
    reward = "clickanywheretocontinue" in normalize(" ".join(m.text for m in bottom))
    return {"outcome": outcome, "reward": reward and outcome is None,
            "repeat": center(repeat[0]) if len(repeat) == 1 else None,
            "matches": [*top, *bottom]}


class EndScreenReader:
    def __init__(self, reader, stop):
        self.reader, self.stop = reader, stop

    def read(self, frame):
        h, w = frame.shape[:2]
        top = self.reader.read(frame, Region(0, 0, max(1, int(w*.8)), max(1, int(h*.55))),
                               scale=1, max_variants=1, min_confidence=.7,
                               cancelled=self.stop.is_set)
        headers = [m for m in top if normalize(m.text) in ('victory','defeat')]
        footer = Region(0, int(h*.75), w, h-int(h*.75))
        if len(headers) == 1:
            xs, ys = zip(*headers[0].corners)
            # OCR boxes can include the decorative header border vertically.
            # Word width gives a steadier estimate of the UI text scale.
            size = max(10, round((max(xs)-min(xs))/len(headers[0].text)*1.7))
            left = max(0, round(min(xs))-size*2)
            start = min(h-1, max(0, round(min(ys))+size*14))
            footer = Region(left, start, min(w-left,size*32),
                            min(h-start,size*14))
        bottom = self.reader.read(frame, footer,
                                  scale=2, max_variants=1, min_confidence=.65,
                                  cancelled=self.stop.is_set)
        return interpret_end(top, bottom)

    def rewards(self, frame, reading):
        h, w = frame.shape[:2]
        matches = self.reader.read(frame, Region(0, int(h*.4), int(w*.8), h-int(h*.4)),
                                   scale=2, max_variants=1, min_confidence=.65,
                                   cancelled=self.stop.is_set)
        return {**reading, "matches": [*reading["matches"], *matches]}


def save_rewards(frame, reading, directory):
    """Capture the current reward area, never the entire game/results screen."""
    directory = Path(directory) / "latest"
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob("reward-*.png"):
        old.unlink()
    def save(name, image):
        ok, data = cv2.imencode(".png", image)
        if not ok:
            raise OSError("Could not encode reward image")
        (directory / name).write_bytes(data.tobytes())
    matches = reading["matches"]
    headers = [m for m in matches if normalize(m.text) == "gainedrewards"]
    buttons = [m for m in matches if normalize(m.text) == "repeatstage"]
    files = []
    reward_text = []
    strip_name = None
    if headers and buttons:
        header, button = headers[0], buttons[0]
        label_height = max(y for x, y in header.corners)-min(y for x, y in header.corners)
        left = max(0, round(min(x for x, y in header.corners)-label_height))
        top = round(max(y for x, y in header.corners)) + 3
        button_height = max(y for x, y in button.corners)-min(y for x, y in button.corners)
        bottom = round(min(y for x, y in button.corners)-1.2*button_height)
        # Derive the reward column from the navigation row, not item names or
        # a fixed number of rewards. This includes every visible row of tiles.
        party = [m for m in matches if normalize(m.text) == "viewparty"]
        if party:
            px, _ = center(party[0])
            bx, _ = center(button)
            right = min(frame.shape[1], round(px + .9*(px-bx)))
        else:
            right = min(frame.shape[1], left + round((bottom-top)*4.1))
        if bottom > top and right > left:
            strip = frame[top:bottom, left:right, :3]
            save("reward-strip.png", strip)
            strip_name = "reward-strip.png"
            reward_text = [m.text for m in matches if left <= center(m)[0] < right
                           and top <= center(m)[1] < bottom]
            hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (0, 95, 100), (179, 255, 255))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                   cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            boxes = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w < 20 or h < 20 or not .55 <= w/h <= 1.5:
                    continue
                for i, (bx, by, bw, bh) in enumerate(boxes):
                    overlap = max(0, min(x+w,bx+bw)-max(x,bx))*max(0,min(y+h,by+bh)-max(y,by))
                    if overlap > .25*min(w*h,bw*bh):
                        left_edge, top_edge = min(x,bx), min(y,by)
                        boxes[i] = (left_edge,top_edge,max(x+w,bx+bw)-left_edge,max(y+h,by+bh)-top_edge)
                        break
                else:
                    boxes.append((x,y,w,h))
            for x, y, w, h in sorted(boxes, key=lambda b:(b[1]//30,b[0])):
                name = f"reward-{len(files)+1:02d}.png"
                save(name, strip[max(0,y-4):y+h+4, max(0,x-4):x+w+4])
                files.append(name)
    (directory / "rewards.json").write_text(json.dumps({
        "outcome": reading["outcome"], "text": reward_text,
        "images": files, "strip_image": strip_name,
    }, indent=2), encoding="utf-8")
    return directory
