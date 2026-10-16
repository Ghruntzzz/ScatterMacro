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
