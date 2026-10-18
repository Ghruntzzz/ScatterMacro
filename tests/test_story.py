import unittest
from threading import Event
from unittest.mock import Mock

import numpy as np

from python_macro.ocr import TextMatch
from python_macro.story import navigate_story, MAP_SCROLL_STEPS


class FastStop(Event):
    def wait(self, timeout=None):
        return self.is_set()


def label(text):
    return TextMatch(text, 0.95, ((10, 10), (30, 10), (30, 20), (10, 20)))


class StoryTests(unittest.TestCase):
    def test_click_order_without_scrolling_when_map_visible(self):
        reader = Mock()
        reader.read.side_effect = [[label(t)] for t in ("PLAY", "Story", "School Grounds")]
        click, log, scroll = Mock(), Mock(), Mock()
        navigate_story("School Grounds", lambda: np.zeros((50, 80, 4)),
                       reader, click, FastStop(), log, scroll=scroll)
        self.assertEqual(click.call_count, 3)
        scroll.assert_not_called()
        self.assertEqual([c.args[0] for c in log.call_args_list if c.args[0].endswith("clicked.")],
                         ["Play clicked.", "Story clicked.", "School Grounds clicked."])

    def test_scroll_down_after_story_when_map_not_visible(self):
        reader = Mock()
        reader.read.side_effect = [[label("Play")], [label("Story")],
                                   [], [], [], [label("Flower Forest")]]
        click, scroll = Mock(), Mock()
        events = []
        click.side_effect = lambda x, y, shape: events.append(("click", x, y))
        scroll.side_effect = lambda steps, x, y, shape: events.append(("scroll", steps, x, y))
        navigate_story("Flower Forest", lambda: np.zeros((100, 200, 4)),
                       reader, click, FastStop(), Mock(), scroll=scroll)
        self.assertEqual(scroll.call_count, 2)
        self.assertEqual(click.call_count, 4)
        self.assertEqual(events[:2], [("click", 20, 15), ("click", 20, 15)])
        self.assertEqual(events[2], ("click", 100, 86))
        self.assertEqual(events[3], ("scroll", MAP_SCROLL_STEPS, 100, 86))
        self.assertEqual(events[4], ("scroll", MAP_SCROLL_STEPS, 100, 86))
        self.assertEqual(events[5], ("click", 20, 15))

    def test_scroll_limit_fails_safely(self):
        reader = Mock()
        reader.read.side_effect = [[label("Play")], [label("Story")]]
        reader.read.return_value = []
        click, scroll = Mock(), Mock()
        with self.assertRaisesRegex(RuntimeError, "downward map-list scrolls"):
            navigate_story("Missing Map", lambda: np.zeros((100, 200, 4)),
                           reader, click, FastStop(), Mock(), scroll=scroll,
                           max_map_scrolls=2)
        self.assertEqual(scroll.call_count, 2)
        self.assertEqual(click.call_count, 3)

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

    def test_cancel_during_scroll_prevents_map_click(self):
        stop = FastStop()
        reader = Mock()
        reader.read.side_effect = [[label("Play")], [label("Story")], [], []]
        scroll = Mock(side_effect=lambda *args: stop.set())
        click = Mock()
        navigate_story("Flower Forest", lambda: np.zeros((100, 200, 4)),
                       reader, click, stop, Mock(), scroll=scroll)
        self.assertEqual(click.call_count, 3)
        self.assertEqual(scroll.call_count, 1)

    def test_timeout_does_not_advance(self):
        click = Mock()
        with self.assertRaisesRegex(RuntimeError, "Play"):
            navigate_story("School Grounds", Mock(), Mock(), click, FastStop(), Mock(), timeout=0)
        click.assert_not_called()
