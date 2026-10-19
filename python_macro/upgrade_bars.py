"""Read the complete, aligned upgrade strip without guessing unclear brightness."""
import cv2
import numpy as np


def read_upgrade_bars(frame, close):
    x, y, w, h = close
    left, top = max(0, x-14*w), max(0, round(y+8*h))
    right, bottom = min(frame.shape[1], x+w), min(frame.shape[0], round(y+9.6*h))
    if bottom <= top or right <= left:
        return None
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[top:bottom, left:right, :3]), cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (15,90,35), (165,255,255))
    mask[:round(h*.6)] = 0
    # Thin panel borders and background streaks can join adjacent rectangles.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            np.ones((max(2,round(h*.12)), max(3,round(w*.19))), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) for c in contours]
    boxes = [b for b in boxes if .6*w <= b[2] <= 14*w and .35*h <= b[3] <= .8*h
             and b[0] > 0 and b[1] > 0 and b[0]+b[2] < right-left and b[1]+b[3] < bottom-top]
    rows = []
    tolerance = max(2, round(h*.1))
    for box in sorted(boxes, key=lambda b:b[1]):
        row = next((r for r in rows if abs(r[0][1]-box[1]) <= tolerance), None)
        if row is None:
            rows.append([box])
        else:
            row.append(box)
    # Read horizontal runs too: background artwork may touch a bar's outer
    # border while its interior and the black gaps remain clearly separated.
    for cy in range(round(h*.8), min(mask.shape[0]-3, round(h*1.05))):
        edges = np.diff(np.r_[False, mask[cy] > 0, False].astype(np.int8))
        runs = [(int(a), cy-4, int(b-a), 9)
                for a,b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
                if .6*w <= b-a <= 14*w and a > 0 and b < mask.shape[1]]
        if runs:
            rows.append(runs)
    readings = []
    for row in rows:
        row.sort(key=lambda b:b[0])
        if not 1 <= len(row) <= 20:
            continue
        widths = [b[2] for b in row]
        span = row[-1][0]+row[-1][2]-row[0][0]
        if not 11*w <= span <= 14*w or max(widths) > min(widths)*1.2:
            continue
        if any(not 0 < b[0]-(a[0]+a[2]) <= .5*w for a,b in zip(row,row[1:])):
            continue
        levels = []
        for bx,by,bw,bh in row:
            px, py = max(2,round(bw*.08)), max(2,round(bh*.15))
            interior = hsv[by+py:by+bh-py, bx+px:bx+bw-px, 2]
            if interior.size == 0:
                levels.append(None)
                continue
            value = float(np.median(interior))
            levels.append(True if value >= 145 else False if value <= 120 else None)
        if any(value is None for value in levels):
            continue
        count = sum(levels)
        if levels != [True]*count + [False]*(len(levels)-count):
            continue
        readings.append((count,len(levels)))
    distinct = set(readings)
    return next(iter(distinct)) if len(distinct) == 1 else None
