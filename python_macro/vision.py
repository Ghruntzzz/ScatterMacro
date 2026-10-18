"""Pure OpenCV preprocessing; no input injection or AHK dependency."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    def crop(self, frame: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
        """Clip a saved client-relative region, retaining its actual origin."""
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Detection region must have positive dimensions")
        left, top = max(0, self.x), max(0, self.y)
        right = min(frame.shape[1], self.x + self.width)
        bottom = min(frame.shape[0], self.y + self.height)
        if right <= left or bottom <= top:
            raise ValueError("Detection region is outside the captured client")
        return frame[top:bottom, left:right].copy(), (left, top)


def text_variants(crop: np.ndarray, scale: int = 4):
    """Yield OCR inputs lazily, stopping at the first confident text match.

    All variants keep the same geometry. Divide OCR coordinates by scale and
    add the clipped region origin to recover client-relative click positions.
    """
    if crop.size == 0 or scale not in range(1, 7):
        raise ValueError("Expected a nonempty image and scale from 1 to 6")
    if crop.ndim == 2:
        gray = crop
    elif crop.ndim == 3 and crop.shape[2] in (3, 4):
        gray = cv2.cvtColor(crop, cv2.COLOR_BGRA2GRAY if crop.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError("Expected grayscale, BGR, or BGRA capture")
    if scale != 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    yield gray
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    yield contrast
    _, binary = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    yield binary

class PlayIconLocator:
    """Locate the bundled teal Play icon, never relying on its small OCR text."""

    def __init__(self, path, min_score=0.86):
        from python_macro.play_reference import play_template
        self.template = play_template()
        self.min_score = min_score
        self.tiles = []
        self.misses = 0
        self.shrink = 0.65
        for scale in (0.65, 0.70, 0.775, 0.85, 0.925, 1.0, 1.075, 1.15,
                      1.225, 1.30, 1.375, 1.45, 1.525, 1.60, 1.75, 1.90):
            size = (round(self.template.shape[1] * scale), round(self.template.shape[0] * scale))
            self.tiles.append(cv2.resize(self.template, size,
                              interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR))

    def __call__(self, frame):
        if frame.ndim != 3 or frame.shape[2] not in (3, 4):
            raise ValueError("Expected BGR or BGRA Roblox screenshot")
        image = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY if frame.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
        # Coarse multi-scale search at reduced resolution, then refine only
        # the strongest three candidates at native resolution.
        small = cv2.resize(image, None, fx=self.shrink, fy=self.shrink,
                           interpolation=cv2.INTER_AREA)
        candidates = []
        for idx, tile in enumerate(self.tiles):
            fast = cv2.resize(tile, None, fx=self.shrink, fy=self.shrink,
                              interpolation=cv2.INTER_AREA)
            if fast.shape[0] >= small.shape[0] or fast.shape[1] >= small.shape[1]:
                continue
            _, score, _, origin = cv2.minMaxLoc(cv2.matchTemplate(small, fast, cv2.TM_CCOEFF_NORMED))
            candidates.append((score, idx, origin))
        best = None
        for _, idx, origin in sorted(candidates, reverse=True)[:3]:
            tile = self.tiles[idx]
            h, w = tile.shape[:2]
            x, y = round(origin[0] / self.shrink), round(origin[1] / self.shrink)
            left, top = max(0, x - 5), max(0, y - 5)
            right, bottom = min(image.shape[1], x + w + 6), min(image.shape[0], y + h + 6)
            roi = image[top:bottom, left:right]
            if roi.shape[1] < w or roi.shape[0] < h:
                continue
            _, score, _, p = cv2.minMaxLoc(cv2.matchTemplate(roi, tile, cv2.TM_CCOEFF_NORMED))
            if best is None or score > best[0]:
                best = (float(score), (left + p[0], top + p[1]), w, h)
        if best is None or best[0] < self.min_score:
            self.misses += 1
            if self.misses % 5:
                return None
            # Recover if downsampling discarded unusual button detail.
            for tile in self.tiles:
                h, w = tile.shape[:2]
                if h >= image.shape[0] or w >= image.shape[1]:
                    continue
                _, score, _, pos = cv2.minMaxLoc(cv2.matchTemplate(image, tile, cv2.TM_CCOEFF_NORMED))
                if best is None or score > best[0]:
                    best = (float(score), pos, w, h)
            if best is None or best[0] < self.min_score:
                return None
        self.misses = 0
        score, (left, top), tw, th = best
        return left + tw // 2, top + round(th * 0.43), score

class StartButtonLocator:
    """Recognize the supplied green Start button and click inside its center."""

    def __init__(self, path, min_score=0.84):
        self.template = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if self.template is None:
            raise RuntimeError("Start button reference image is missing.")
        self.min_score = min_score
        self.misses = 0
        self.tiles = []
        for scale in (0.70, 0.80, 0.85, 0.90, 1.0, 1.10, 1.20, 1.30, 1.45, 1.60):
            size = (round(self.template.shape[1] * scale), round(self.template.shape[0] * scale))
            self.tiles.append(cv2.resize(self.template, size,
                              interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR))

    def __call__(self, frame):
        if frame.ndim != 3 or frame.shape[2] not in (3, 4):
            raise ValueError("Expected color screenshot.")
        image = np.ascontiguousarray(frame[:, :, :3])
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (28, 65, 65), (94, 255, 255))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if not (self.template.shape[1] * 0.5 <= w <= self.template.shape[1] * 2
                    and self.template.shape[0] * 0.5 <= h <= self.template.shape[0] * 2):
                continue
            # Only search green button-sized regions, with a margin for borders.
            pad = max(8, round(h * 0.3))
            left, top = max(0, x - pad), max(0, y - pad)
            roi = image[top:min(image.shape[0], y+h+pad), left:min(image.shape[1], x+w+pad)]
            for tile in self.tiles:
                th, tw = tile.shape[:2]
                if tw > roi.shape[1] or th > roi.shape[0]:
                    continue
                _, score, _, origin = cv2.minMaxLoc(cv2.matchTemplate(roi, tile, cv2.TM_CCOEFF_NORMED))
                if best is None or score > best[0]:
                    best = (score, (left + origin[0], top + origin[1]), tw, th)
        if best is None or best[0] < self.min_score:
            self.misses += 1
            if self.misses % 4:
                return None
            # Preserve recovery if green artwork touches the button and merges
            # contours. This expensive fallback is not run on every frame.
            for tile in self.tiles:
                th, tw = tile.shape[:2]
                if tw > image.shape[1] or th > image.shape[0]:
                    continue
                _, score, _, origin = cv2.minMaxLoc(cv2.matchTemplate(image, tile, cv2.TM_CCOEFF_NORMED))
                if best is None or score > best[0]:
                    best = (score, origin, tw, th)
            if best is None or best[0] < self.min_score:
                return None
        score, (x, y), tw, th = best
        # Check that the full candidate is actually green, rather than a
        # high-correlating text label or another dark element on screen.
        patch = image[y:y + th, x:x + tw]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (28, 65, 65), (94, 255, 255))
        if cv2.countNonZero(green) < 0.45 * tw * th:
            return None
        self.misses = 0
        return x + tw // 2, y + th // 2, float(score)
