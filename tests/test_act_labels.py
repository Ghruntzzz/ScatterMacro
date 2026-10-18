import unittest
import cv2
import numpy as np
from python_macro.act_labels import ActLabelLocator, _ORDER


class ActLabelTests(unittest.TestCase):
    def test_each_act_matches_only_label_area_without_stars(self):
        locator = ActLabelLocator()
        frame = np.full((480, 320, 3), 18, np.uint8)
        for k, act in enumerate(_ORDER):
            img = locator.gray[k * 22:(k + 1) * 22]
            frame[50 + k * 52:72 + k * 52, 35:72, :] = img[:, :, None]
        for k, act in enumerate(_ORDER):
            point = locator(frame, act)
            self.assertIsNotNone(point, act)
            self.assertAlmostEqual(point[0], 53, delta=1)
            self.assertAlmostEqual(point[1], 61 + 52 * k, delta=1)
            self.assertGreater(point[2], 0.90)

    def test_refuses_empty_frame_and_unknown_act(self):
        locator = ActLabelLocator()
        self.assertIsNone(locator(np.zeros((480, 320, 3), np.uint8), "Act 5"))
        with self.assertRaises(ValueError):
            locator(np.zeros((480, 320, 3), np.uint8), "Act 12")
