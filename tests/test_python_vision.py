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
        from python_macro.play_reference import play_template
        template = cv2.cvtColor(play_template(), cv2.COLOR_GRAY2BGR)
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

    def test_start_button_reference_clicks_its_center(self):
        from python_macro.vision import StartButtonLocator
        path = Path(__file__).resolve().parents[1] / "assets" / "start-button-template.png"
        locator = StartButtonLocator(path)
        template = cv2.imread(str(path))
        self.assertEqual(template.shape[:2], (44, 150))
        for factor in (1.0, 1.2, 0.85):
            scaled = cv2.resize(template, None, fx=factor, fy=factor)
            h, w = scaled.shape[:2]
            canvas = np.full((270, 350, 4), 20, dtype=np.uint8)
            canvas[64:64+h, 82:82+w, :3] = scaled
            result = locator(canvas)
            self.assertIsNotNone(result, str(factor))
            self.assertLessEqual(abs(result[0] - (82 + w // 2)), 2)
            self.assertLessEqual(abs(result[1] - (64 + h // 2)), 2)

    def test_start_button_rejects_empty_client_image(self):
        from python_macro.vision import StartButtonLocator
        path = Path(__file__).resolve().parents[1] / "assets" / "start-button-template.png"
        locator = StartButtonLocator(path)
        self.assertIsNone(locator(np.zeros((220, 350, 4), dtype=np.uint8)))

    def test_start_game_accepts_normal_and_highlighted_states(self):
        from python_macro.vision import StartButtonLocator
        assets = Path(__file__).resolve().parents[1] / 'assets'
        locator = StartButtonLocator(assets / 'start-game-template.png')
        for name in ('start-game-template.png', 'start-game-highlighted.png'):
            reference = cv2.imread(str(assets / name))
            for factor in (0.8, 1.0, 1.2, 1.6):
                with self.subTest(name=name, factor=factor):
                    scaled = cv2.resize(reference, None, fx=factor, fy=factor,
                                        interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_LINEAR)
                    h, w = scaled.shape[:2]
                    frame = np.full((300, 600, 4), 20, np.uint8)
                    frame[100:100+h, 110:110+w, :3] = scaled
                    hit = locator(frame)
                    self.assertIsNotNone(hit)
                    self.assertLessEqual(abs(hit[0] - (110+w//2)), 2)
                    self.assertLessEqual(abs(hit[1] - (100+h//2)), 2)

    def test_start_game_rejects_empty_and_other_button(self):
        from python_macro.vision import StartButtonLocator
        assets = Path(__file__).resolve().parents[1] / 'assets'
        locator = StartButtonLocator(assets / 'start-game-template.png')
        frame = np.full((300, 600, 3), 20, np.uint8)
        other = cv2.imread(str(assets / 'boss-rush-continue.png'))
        h, w = other.shape[:2]
        frame[80:80+h, 90:90+w] = other
        for _ in range(4):
            self.assertIsNone(locator(frame))

    def test_start_reuses_scaled_tiles(self):
        from unittest.mock import patch
        from python_macro.vision import StartButtonLocator
        path = Path(__file__).resolve().parents[1] / 'assets/start-button-template.png'
        locator = StartButtonLocator(path)
        canvas = np.full((250, 350, 3), 20, np.uint8)
        h, w = locator.template.shape[:2]
        canvas[50:50+h, 60:60+w] = locator.template
        with patch('python_macro.vision.cv2.resize', side_effect=AssertionError('Unexpected per-frame resize')):
            self.assertIsNotNone(locator(canvas))
            self.assertIsNotNone(locator(canvas))

    def test_start_fallback_handles_connected_green_background(self):
        from python_macro.vision import StartButtonLocator
        path = Path(__file__).resolve().parents[1] / 'assets/start-button-template.png'
        locator = StartButtonLocator(path)
        canvas = np.full((300, 700, 3), (0, 180, 0), np.uint8)
        h, w = locator.template.shape[:2]
        canvas[70:70+h, 90:90+w] = locator.template
        result = None
        for _ in range(4):
            result = locator(canvas)
            if result is not None:
                break
        self.assertIsNotNone(result)
        self.assertLessEqual(abs(result[0] - (90 + w // 2)), 2)
