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
        first_results = iter([[label("Play")], [label("Story")]])
        reader.read.side_effect = lambda *args, **kwargs: next(first_results, [])
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

    def test_image_play_click_waits_for_story_confirmation(self):
        reader = Mock()
        reader.read.side_effect = [[], [label("Story")], [label("Story")],
                                   [label("Flower Forest")]]
        click, log = Mock(), Mock()
        navigate_story("Flower Forest", lambda: np.zeros((120, 160, 4)),
                       reader, click, FastStop(), log,
                       find_play=lambda frame: (45, 32, 0.99))
        self.assertEqual(click.call_count, 3)
        self.assertEqual(click.call_args_list[0].args[:2], (45, 32))
        self.assertTrue(any("Play click verified" in c.args[0] for c in log.call_args_list))

    def test_unconfirmed_play_button_never_reports_success(self):
        reader, click, log = Mock(), Mock(), Mock()
        reader.read.return_value = []
        with self.assertRaisesRegex(RuntimeError, "could not be verified"):
            navigate_story("School Grounds", lambda: np.zeros((120, 160, 4)),
                           reader, click, FastStop(), log,
                           find_play=lambda frame: (45, 32, 0.99))
        self.assertEqual(click.call_count, 3)
        self.assertFalse(any("Play click verified" in c.args[0] for c in log.call_args_list))

    def test_missing_play_image_does_not_fall_back_to_ocr_word(self):
        reader, click = Mock(), Mock()
        with self.assertRaisesRegex(RuntimeError, "could not be verified"):
            navigate_story("School Grounds", lambda: np.zeros((120, 160, 4)),
                           reader, click, FastStop(), Mock(), find_play=lambda frame: None,
                           timeout=0.02)
        click.assert_not_called()
        reader.read.assert_not_called()

    def test_stopping_during_play_validation_prevents_later_click(self):
        stop = FastStop()
        reader, click = Mock(), Mock()
        reader.read.side_effect = lambda *a, **kw: stop.set() or []
        navigate_story("School Grounds", lambda: np.zeros((120, 160, 4)),
                       reader, click, stop, Mock(), find_play=lambda frame: (45, 32, 0.99))
        self.assertEqual(click.call_count, 1)
