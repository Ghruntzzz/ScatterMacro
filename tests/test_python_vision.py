import unittest

import numpy as np

from python_macro.vision import Region, text_variants, PlayIconLocator
from pathlib import Path
import cv2


class PythonVisionTests(unittest.TestCase):
    def test_crop_preserves_client_coordinate_origin(self):
        frame = np.zeros((60, 100, 4), dtype=np.uint8)
        crop, origin = Region(-5, 10, 30, 20).crop(frame)
        self.assertEqual(origin, (0, 10))
        self.assertEqual(crop.shape, (20, 25, 4))
        with self.assertRaises(ValueError):
            Region(100, 0, 20, 20).crop(frame)

    def test_variants_preserve_geometry_and_source(self):
        frame = np.full((15, 40, 4), 40, dtype=np.uint8)
        frame[5:9, 8:30, :3] = 90
        original = frame.copy()
        variants = list(text_variants(frame, 4))
        self.assertEqual(len(variants), 3)
        for variant in variants:
            self.assertEqual(variant.shape, (60, 160))
        self.assertTrue(np.array_equal(original, frame))
        self.assertTrue(set(np.unique(variants[-1])).issubset({0, 255}))

    def test_visual_template_targets_icon_above_its_caption(self):
        path = Path(__file__).resolve().parents[1] / "assets" / "play-button-template.png"
        locator = PlayIconLocator(path)
        template = cv2.imread(str(path))
        for factor in (1.0, 1.3, 0.85):
            scaled = cv2.resize(template, None, fx=factor, fy=factor)
            h, w = scaled.shape[:2]
            frame = np.zeros((230, 320, 4), dtype=np.uint8)
            frame[:, :, :3] = (20, 28, 30)
            frame[50:50 + h, 90:90 + w, :3] = scaled
            result = locator(frame)
            self.assertIsNotNone(result, msg=str(factor))
            x, y, confidence = result
            self.assertLessEqual(abs(x - (90 + w // 2)), 2)
            self.assertLessEqual(abs(y - (50 + round(h * 0.43))), 2)
            self.assertGreater(confidence, 0.86)

    def test_visual_template_rejects_blank_background(self):
        path = Path(__file__).resolve().parents[1] / "assets" / "play-button-template.png"
        locator = PlayIconLocator(path)
        frame = np.zeros((230, 320, 4), dtype=np.uint8)
        frame[:, :, :3] = (20, 28, 30)
        self.assertIsNone(locator(frame))
