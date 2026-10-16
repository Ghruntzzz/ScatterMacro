import unittest

import numpy as np

from python_macro.vision import Region, text_variants


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
