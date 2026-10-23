"""On-demand OCR for captured client regions; never injects input."""
from dataclasses import dataclass
from threading import Lock

import numpy as np

from python_macro.vision import Region, text_variants


@dataclass(frozen=True)
class TextMatch:
    text: str
    confidence: float
    corners: tuple[tuple[float, float], ...]


class TextReader:
    """Reuse one engine. Call from a worker, not the dashboard UI thread.

    accept can validate expected text or the number of titles before ending
    retries. Confidence alone does not prove that a whole screen was read.
    """

    def __init__(self, engine=None):
        self._engine = engine
        self._lock = Lock()

    def read(self, frame, region: Region, *, scale=3, min_confidence=0.65,
             accept=None, max_variants=3, cancelled=None) -> list[TextMatch]:
        if not 0 <= min_confidence <= 1:
            raise ValueError("Confidence must be between zero and one")
        if max_variants not in (1, 2, 3):
            raise ValueError("Expected one to three OCR passes")
        crop, (left, top) = region.crop(frame)
        best = []
        with self._lock:
            if cancelled is not None and cancelled():
                return []
            if self._engine is None:
                try:
                    from rapidocr import RapidOCR
                except ImportError as exc:
                    raise RuntimeError("Install the macro OCR requirements first") from exc
                # Game UI is upright. Bound detector cost without shrinking
                # small crops; recognition still receives the source pixels.
                self._engine = RapidOCR(params={
                    "Global.use_cls": False,
                    "Det.limit_type": "max",
                    "Det.limit_side_len": 1280,
                    "EngineConfig.onnxruntime.intra_op_num_threads": 4,
                    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                })
            from itertools import islice
            for image in islice(text_variants(crop, scale), max_variants):
                if cancelled is not None and cancelled():
                    return []
                result = self._engine(image)
                matches = []
                if result is not None and result.txts is not None:
                    for text, score, box in zip(result.txts, result.scores, result.boxes):
                        if not text.strip() or not np.isfinite(score) or score < min_confidence:
                            continue
                        points = np.asarray(box, dtype=float)
                        if points.shape != (4, 2) or not np.isfinite(points).all():
                            continue
                        corners = tuple((float(x / scale + left), float(y / scale + top))
                                        for x, y in points)
                        matches.append(TextMatch(text.strip(), float(score), corners))
                if accept is not None and accept(matches):
                    return matches
                if (len(matches), sum(m.confidence for m in matches)) > (
                        len(best), sum(m.confidence for m in best)):
                    best = matches
        return best
