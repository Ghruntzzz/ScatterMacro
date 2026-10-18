import unittest
from threading import Event
from unittest.mock import Mock

import numpy as np

from python_macro.ocr import TextMatch
from python_macro.story import (
    navigate_story, MAP_SCROLL_STEPS, MAP_SCROLL_SETTLE,
    is_act_label, validate_act, validate_difficulty,
)


class FastStop(Event):
    def wait(self, timeout=None):
        return self.is_set()


def label(text):
    return TextMatch(text, 0.95, ((10, 10), (30, 10), (30, 20), (10, 20)))


class StoryTests(unittest.TestCase):
    def test_skip_play_starts_at_story_when_play_menu_already_verified(self):
        reader = Mock()
        reader.read.side_effect = [[label("Story")], [label("School Grounds")]]
        click = Mock()
        navigate_story("School Grounds", lambda: np.zeros((50, 80, 4)),
                       reader, click, FastStop(), Mock(), skip_play=True)
        self.assertEqual(click.call_count, 2)

    def test_click_order_without_scrolling_when_map_visible(self):
        reader = Mock()
        reader.read.side_effect = [[label(t)] for t in ("PLAY", "Story", "School Grounds")]
        click, log, scroll = Mock(), Mock(), Mock()
        navigate_story("School Grounds", lambda: np.zeros((50, 80, 4)),
                       reader, click, FastStop(), log, scroll=scroll)
        self.assertEqual(click.call_count, 3)
        scroll.assert_not_called()
        self.assertTrue(any("Story map selected." in c.args[0] for c in log.call_args_list))

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
        self.assertTrue(any("Play menu opened." in c.args[0] for c in log.call_args_list))

    def test_unconfirmed_play_button_never_reports_success(self):
        reader, click, log = Mock(), Mock(), Mock()
        reader.read.return_value = []
        with self.assertRaisesRegex(RuntimeError, "Play did not open the Story menu"):
            navigate_story("School Grounds", lambda: np.zeros((120, 160, 4)),
                           reader, click, FastStop(), log,
                           find_play=lambda frame: (45, 32, 0.99))
        self.assertEqual(click.call_count, 3)
        self.assertFalse(any("Play menu opened." in c.args[0] for c in log.call_args_list))

    def test_missing_play_image_does_not_fall_back_to_ocr_word(self):
        reader, click = Mock(), Mock()
        with self.assertRaisesRegex(RuntimeError, "Play did not open the Story menu"):
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


    def test_play_retries_only_confirmed_sendinput_click_function(self):
        reader = Mock()
        reader.read.side_effect = ([[]] * 6 + [[label("Story")],
                                   [label("Story")], [label("Flower Forest")]])
        click, log = Mock(), Mock()
        navigate_story("Flower Forest", lambda: np.zeros((120, 160, 4)),
                       reader, click, FastStop(), log,
                       find_play=lambda f: (45, 32, 0.99))
        self.assertEqual(click.call_count, 4)
        self.assertEqual(click.call_args_list[0].args[:2], (45, 32))
        self.assertEqual(click.call_args_list[1].args[:2], (45, 32))
        self.assertFalse(any("SendInput" in c.args[0] or "attempt" in c.args[0]
                             for c in log.call_args_list))

    def test_saved_settings_full_story_normal(self):
        reader = Mock()
        reader.read.side_effect = [[label(t)] for t in
                                   ("Story", "School Grounds", "1",
                                    "Select Stage", "Start")]
        click, log = Mock(), Mock()
        navigate_story("School Grounds", lambda: np.zeros((100, 200, 4)),
                       reader, click, FastStop(), log,
                       skip_play=True, act_name="Act 1", difficulty="Normal")
        self.assertEqual(click.call_count, 5)
        self.assertTrue(any("Normal difficulty" in c.args[0] for c in log.call_args_list))
        self.assertTrue(any("Start selected" in c.args[0] for c in log.call_args_list))

    def test_saved_settings_hard_selection(self):
        reader = Mock()
        reader.read.side_effect = [[label(t)] for t in
                                   ("Story", "Flower Forest", "Act 5", "Hard",
                                    "Select Stage", "Start")]
        click = Mock()
        navigate_story("Flower Forest", lambda: np.zeros((100, 200, 4)),
                       reader, click, FastStop(), Mock(),
                       skip_play=True, act_name="Act 5", difficulty="Hard")
        self.assertEqual(click.call_count, 6)

    def test_act_locator_path_avoids_ocr_and_stars(self):
        reader = Mock()
        reader.read.side_effect = [[label("Story")], [label("School Grounds")],
                                   [label("Select Stage")], [label("Start")]]
        matcher = Mock(return_value=(50, 83, 0.98))
        click = Mock()
        navigate_story("School Grounds", lambda: np.zeros((100, 200, 4)),
                       reader, click, FastStop(), Mock(), skip_play=True,
                       act_name="Act 3", find_act=matcher)
        matcher.assert_called_once()
        self.assertEqual(matcher.call_args.args[1], "Act 3")
        self.assertEqual(click.call_count, 5)
        self.assertEqual(click.call_args_list[2].args[:2], (50, 83))

    def test_infinite_and_mastery_skip_difficulty(self):
        for act, printed in (("Infinite", "∞"), ("Mastery", "M")):
            with self.subTest(act=act):
                reader = Mock()
                reader.read.side_effect = [[label(t)] for t in
                                           ("Story", "School Grounds", printed,
                                            "Select Stage", "Start")]
                click = Mock()
                navigate_story("School Grounds", lambda: np.zeros((100, 200, 4)),
                               reader, click, FastStop(), Mock(),
                               skip_play=True, act_name=act, difficulty="Hard")
                self.assertEqual(click.call_count, 5)
                self.assertEqual(reader.read.call_count, 5)

    def test_act_match_is_exact_and_not_a_partial_number(self):
        self.assertTrue(is_act_label("5", "Act 5"))
        self.assertTrue(is_act_label("Act 5", "Act 5"))
        self.assertTrue(is_act_label("∞", "Infinite"))
        self.assertTrue(is_act_label("Infinity", "Infinite"))
        self.assertTrue(is_act_label("M", "Mastery"))
        self.assertFalse(is_act_label("15", "Act 5"))
        self.assertFalse(is_act_label("8", "Infinite"))
        self.assertFalse(is_act_label("Menu", "Mastery"))
        with self.assertRaises(ValueError):
            validate_act("Act 6")
        with self.assertRaises(ValueError):
            validate_difficulty("Expert")

    def test_map_scroll_is_quicker_and_quiet(self):
        self.assertEqual(MAP_SCROLL_STEPS, -3)
        self.assertLess(MAP_SCROLL_SETTLE, 0.3)
        reader = Mock()
        reader.read.side_effect = [[label("Story")], [], [], [label("School Grounds")]]
        scroll, log, click = Mock(), Mock(), Mock()
        navigate_story("School Grounds", lambda: np.zeros((100, 200, 4)),
                       reader, click, FastStop(), log, scroll=scroll,
                       skip_play=True)
        scroll.assert_called_once_with(-3, 100, 86, (100, 200, 4))
        self.assertFalse(any("scroll" in c.args[0].lower()
                             or "click" in c.args[0].lower()
                             for c in log.call_args_list))

    def test_full_flow_rejects_ambiguous_act_without_wrong_click(self):
        reader = Mock()
        calls = 0
        def reads(*args, **kw):
            nonlocal calls
            calls += 1
            if calls == 1:
                return [label("Story")]
            if calls == 2:
                return [label("School Grounds")]
            return [label("1"), label("1")]
        reader.read.side_effect = reads
        click = Mock()
        with self.assertRaisesRegex(RuntimeError, "Could not uniquely identify Act 1"):
            navigate_story("School Grounds", lambda: np.zeros((100, 200, 4)),
                           reader, click, FastStop(), Mock(),
                           timeout=0.2, skip_play=True, act_name="Act 1")
        self.assertEqual(click.call_count, 2)
