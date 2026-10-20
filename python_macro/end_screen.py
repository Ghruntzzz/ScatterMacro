"""OCR end-screen recognition and local reward evidence for future webhooks."""
import json
import re
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
    prompt = " ".join(m.text for m in bottom)
    compact = normalize(prompt)
    closing = "clickanywheretoclose" in compact
    reward = closing or "clickanywheretocontinue" in compact
    pages = {(int(a),int(b)) for a,b in re.findall(r'\[\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\]',prompt)
             if 1 <= int(a) <= int(b) <= 50}
    clicks = 1
    if reward and not closing and len(pages) == 1:
        current, total = pages.pop()
        clicks = total-current+1
    return {"outcome": outcome, "reward": reward and outcome is None,
            "reward_clicks": clicks,
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
    """Save the Roblox client screenshot and dynamically grouped reward text."""
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
    save("roblox.png", frame[:, :, :3])
    headers = [m for m in matches if normalize(m.text) == "gainedrewards"]
    buttons = [m for m in matches if normalize(m.text) == "repeatstage"]
    files = []
    reward_text = []
    strip_name = None
    rewards = []
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
                tile_matches = [m for m in matches if left+x-5 <= center(m)[0] < left+x+w+5
                                and top+y-8 <= center(m)[1] < top+y+h+5]
                rewards.append(reward_label(tile_matches, top+y, h))
    (directory / "rewards.json").write_text(json.dumps({
        "outcome": reading["outcome"], "text": reward_text,
        "images": files, "strip_image": strip_name,
        "rewards": rewards, "stats": result_stats(matches), "screenshot": "roblox.png",
    }, indent=2), encoding="utf-8")
    return directory


def reward_label(matches, top, height):
    """Use quantity and bottom captions, not decorative lettering inside icons."""
    quantities = {m.text.strip() for m in matches if re.fullmatch(r'[\d,.]+\s*[xX]',m.text.strip())}
    quantity = next(iter(quantities)) if len(quantities) == 1 else '?x'
    names = []
    for m in sorted(matches, key=lambda m:(center(m)[1],center(m)[0])):
        text = m.text.strip()
        if center(m)[1] < top + height*.65 or re.fullmatch(r'[\d,.]+\s*[xX]',text):
            continue
        if normalize(text) not in {normalize(n) for n in names}:
            names.append(text)
    return quantity + ' ' + (' '.join(names) or 'Unread reward')


def result_stats(matches):
    stats = {}
    for title in ('Clear Time','Total Yen','Total Kills','Total Damage'):
        anchors = [m for m in matches if normalize(m.text) == normalize(title)]
        for anchor in anchors:
            ax, ay = center(anchor)
            height = max(y for x,y in anchor.corners)-min(y for x,y in anchor.corners)
            choices = [m for m in matches if center(m)[0] > ax
                       and abs(center(m)[1]-ay) <= max(8,height*.65)
                       and re.fullmatch(r'[\d,.]+(?:\s*[hms]\s*[\d,.]*\s*[hms]?)*',m.text.strip(),re.I)]
            if choices:
                stats[title] = min(choices,key=lambda m:center(m)[0]).text
                break
    return stats
