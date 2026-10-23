from pathlib import Path
from threading import Event
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from python_macro.vision import StoryButtonLocator
from python_macro.story_verified import navigate_story_checked
from python_macro.input import RobloxClient


class StoryImageTests(unittest.TestCase):
    def test_template_scales_and_blank_screen(self):
        path = Path(__file__).resolve().parents[1] / "assets/story-button-template.png"
        locator = StoryButtonLocator(path)
        template = cv2.imread(str(path))
        for scale in (0.8, 1.0, 1.5):
            image = cv2.resize(template, None, fx=scale, fy=scale)
            h, w = image.shape[:2]
            frame = np.zeros((600, 900, 3), np.uint8)
            frame[100:100+h, 300:300+w] = image
            found = locator(frame)
            self.assertIsNotNone(found)
            self.assertLessEqual(abs(found[0] - (300 + w // 2)), 2)
            self.assertLessEqual(abs(found[1] - (100 + h // 2)), 2)
        self.assertIsNone(locator(np.zeros_like(frame)))

    def test_story_image_bypasses_ocr(self):
        frame = np.zeros((600, 900, 3), np.uint8)
        reader = Mock()
        finder = Mock(return_value=(310,110,0.99))
        def press(label, locate, *args, **kwargs):
            self.assertEqual(label, "Story")
            self.assertEqual(locate(frame), (310,110,0.99))
            return False
        with patch("python_macro.story_verified.click_and_confirm", side_effect=press):
            navigate_story_checked("School Grounds", Mock(), reader, Mock(), Event(),
                                   Mock(), skip_play=True, find_story=finder)
        reader.read.assert_not_called()

    def test_start_has_its_own_settle_time(self):
        client = RobloxClient.__new__(RobloxClient)
        client._direct_click = Mock(return_value=True)
        self.assertTrue(client.start_click(10,20,(600,900,3)))
        client._direct_click.assert_called_once_with(10,20,(600,900,3),
                                                     method="input", settle_seconds=0.35)
