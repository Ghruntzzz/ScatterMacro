import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from python_macro.ocr import TextReader
from python_macro.vision import Region


def result(text="Continue", score=0.95):
    return SimpleNamespace(txts=[text], scores=[score],
                           boxes=[[[0, 0], [30, 0], [30, 15], [0, 15]]])


class OCRTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((60, 120, 4), dtype=np.uint8)
        self.region = Region(10, 20, 50, 20)

    def test_coordinates_and_expected_text_stop(self):
        engine = Mock(return_value=result())
        matches = TextReader(engine).read(self.frame, self.region,
                                         accept=lambda items: any(m.text == "Continue" for m in items))
        self.assertEqual(engine.call_count, 1)
        self.assertEqual(matches[0].corners[2], (20.0, 25.0))

    def test_retries_low_confidence_and_empty_results(self):
        engine = Mock(side_effect=[result(score=0.2), None, result()])
        matches = TextReader(engine).read(self.frame, self.region)
        self.assertEqual(engine.call_count, 3)
        self.assertEqual([m.text for m in matches], ["Continue"])

    def test_no_text_is_not_success(self):
        self.assertEqual(TextReader(Mock(return_value=None)).read(self.frame, self.region), [])

    def test_invalid_confidence(self):
        with self.assertRaises(ValueError):
            TextReader(Mock()).read(self.frame, self.region, min_confidence=2)
