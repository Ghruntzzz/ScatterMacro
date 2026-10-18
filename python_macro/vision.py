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
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    yield gray
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    yield contrast
    _, binary = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    yield binary

class PlayIconLocator:
    """Locate the bundled teal Play icon, never relying on its small OCR text."""

    def __init__(self, path, min_score=0.86):
        self.template = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if self.template is None:
            raise RuntimeError("The Play icon reference image is missing.")
        self.min_score = min_score

    def __call__(self, frame):
        if frame.ndim != 3 or frame.shape[2] not in (3, 4):
            raise ValueError("Expected BGR or BGRA Roblox screenshot")
        image = np.ascontiguousarray(frame[:, :, :3])
        height, width = image.shape[:2]
        best = None
        for scale in (0.70, 0.775, 0.85, 0.925, 1.0, 1.075, 1.15,
                      1.225, 1.30, 1.375, 1.45, 1.525, 1.60):
            tw, th = (round(self.template.shape[1] * scale),
                      round(self.template.shape[0] * scale))
            if tw >= width or th >= height:
                continue
            method = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
            template = cv2.resize(self.template, (tw, th), interpolation=method)
            scores = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, origin = cv2.minMaxLoc(scores)
            if best is None or score > best[0]:
                best = (float(score), origin, tw, th)
        if best is None or best[0] < self.min_score:
            return None
        confidence, (left, top), tw, th = best
        return left + tw // 2, top + round(th * 0.43), confidence

class StartButtonLocator:
    """Recognize the supplied green Start button and click inside its center."""

    def __init__(self, path, min_score=0.84):
        self.template = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if self.template is None:
            raise RuntimeError("Start button reference image is missing.")
        self.min_score = min_score

    def __call__(self, frame):
        if frame.ndim != 3 or frame.shape[2] not in (3, 4):
            raise ValueError("Expected color screenshot.")
        image = np.ascontiguousarray(frame[:, :, :3])
        best = None
        for scale in (0.70, 0.80, 0.85, 0.90, 1.0, 1.10, 1.20, 1.30, 1.45, 1.60):
            tw = round(self.template.shape[1] * scale)
            th = round(self.template.shape[0] * scale)
            if tw >= image.shape[1] or th >= image.shape[0]:
                continue
            method = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
            tile = cv2.resize(self.template, (tw, th), interpolation=method)
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
        return x + tw // 2, y + th // 2, float(score)
