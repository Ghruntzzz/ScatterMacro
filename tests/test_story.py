import unittest
from threading import Event
from unittest.mock import Mock

import numpy as np

from python_macro.ocr import TextMatch
from python_macro.story import navigate_story


class FastStop(Event):
    def wait(self, timeout=None):
        return self.is_set()


def label(text):
    return TextMatch(text, 0.95, ((10, 10), (30, 10), (30, 20), (10, 20)))


class StoryTests(unittest.TestCase):
    def test_click_order(self):
        reader = Mock()
        reader.read.side_effect = [[label(t)] for t in ("PLAY", "Story", "School Grounds")]
        click, log = Mock(), Mock()
        navigate_story("School Grounds", lambda: np.zeros((50, 80, 4)),
                       reader, click, FastStop(), log)
        self.assertEqual(click.call_count, 3)
        self.assertEqual([c.args[0] for c in log.call_args_list if c.args[0].endswith("clicked.")],
                         ["Play clicked.", "Story clicked.", "School Grounds clicked."])

    def test_cancel_during_ocr_prevents_click(self):
        stop = FastStop()
        reader = Mock()
        def read(*args, **kwargs):
            stop.set()
            return [label("Play")]
        reader.read.side_effect = read
        click = Mock()
        navigate_story("School Grounds", lambda: np.zeros((50, 80, 4)),
                       reader, click, stop, Mock())
        click.assert_not_called()

    def test_timeout_does_not_advance(self):
        click = Mock()
        with self.assertRaisesRegex(RuntimeError, "Play"):
            navigate_story("School Grounds", Mock(), Mock(), click, FastStop(), Mock(), timeout=0)
        click.assert_not_called()
