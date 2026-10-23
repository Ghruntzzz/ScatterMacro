from pathlib import Path
import unittest
from unittest.mock import Mock
from threading import Event
import cv2
import numpy as np
from python_macro.upgrade_bars import read_upgrade_bars
from python_macro.unit_actions import UnitPanel

FIXTURES = Path(__file__).parent / "fixtures"


class UpgradeBarTests(unittest.TestCase):
    def test_manual_upgrade_scan_does_not_call_ocr(self):
        panel=UnitPanel.__new__(UnitPanel)
        panel.reader=Mock()
        panel.stop=Event()
        panel.close_icon=Mock(return_value=(347,23,27,25))
        image=cv2.imread(str(FIXTURES/"upgrades-2-of-3.png"))
        self.assertEqual(panel.read(image,need_upgrade=True)["upgrade"],(2,3))
        panel.reader.read.assert_not_called()

    def test_supplied_panels(self):
        # The 7/7 attachment clips the close icon at its upper edge, so these
        # test the strip reader with known icon geometry, not icon recognition.
        for name, close, expected in [
            ("0-of-7", (343,16,27,25), (0,7)),
            ("2-of-3", (347,23,27,25), (2,3)),
            ("7-of-7", (347,10,27,25), (7,7)),
            ("0-of-5", (339,15,27,25), (0,5)),
        ]:
            with self.subTest(name=name):
                image=cv2.imread(str(FIXTURES/f"upgrades-{name}.png"))
                self.assertEqual(read_upgrade_bars(image,close), expected)
                canvas=np.zeros((700,1000,3),np.uint8)
                h,w=image.shape[:2]
                canvas[150:150+h,300:300+w]=image
                self.assertEqual(read_upgrade_bars(canvas,(close[0]+300,close[1]+150,*close[2:])),expected)

    def test_blank_and_missing_bar_are_not_maxed(self):
        image=cv2.imread(str(FIXTURES/"upgrades-7-of-7.png"))
        self.assertIsNone(read_upgrade_bars(np.zeros_like(image),(347,10,27,25)))
        image[225:245,108:160]=0
        self.assertIsNone(read_upgrade_bars(image,(347,10,27,25)))

    def test_nonconsecutive_lit_bars_rejected(self):
        image=cv2.imread(str(FIXTURES/"upgrades-7-of-7.png"))
        image[229:243,64:108]=(image[229:243,64:108]*.5).astype(np.uint8)
        self.assertIsNone(read_upgrade_bars(image,(347,10,27,25)))
