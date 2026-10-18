import unittest
from threading import Event
from unittest.mock import Mock
import numpy as np

from python_macro.click_diagnostics import PLAY_METHODS, story_visible, test_play_methods
from python_macro.ocr import TextMatch


def match(text):
    return TextMatch(text, 0.99, ((8, 8), (20, 8), (20, 19), (8, 19)))


class FastStop(Event):
    def wait(self, duration=None):
        return self.is_set()


class ClickDiagnosticsTests(unittest.TestCase):
    def client(self):
        c = Mock()
        c.focus_roblox.return_value = True
        c.capture.return_value = np.zeros((90, 140, 4), dtype=np.uint8)
        for _, method in PLAY_METHODS:
            getattr(c, method).return_value = True
        return c

    def test_methods_list_is_distinct_and_has_four_methods(self):
        self.assertEqual(len(PLAY_METHODS), 4)
        self.assertEqual(len({key for _, key in PLAY_METHODS}), 4)

    def test_first_success_avoids_remaining_clicks(self):
        client, log = self.client(), Mock()
        reader = Mock()
        # Pre-click no Story; after first click Story appears.
        reader.read.side_effect = [[], [match("Story")]]
        found = test_play_methods(client, lambda f: (48, 60, 0.98), reader,
                                  FastStop(), log)
        self.assertEqual(found, PLAY_METHODS[0][0])
        client.direct_click.assert_called_once()
        for _, method in PLAY_METHODS[1:]:
            getattr(client, method).assert_not_called()
        self.assertTrue(any("SUCCESS:" in a.args[0] for a in log.call_args_list))

    def test_unconfirmed_method_moves_to_next_until_story_is_visible(self):
        client, log = self.client(), Mock()
        reader = Mock()
        # Method 1: initial check + 6 failure checks.
        # Method 2: initial check + Story success check.
        reader.read.side_effect = [[]] * 8 + [[match("Story")]]
        result = test_play_methods(client, lambda f: (48, 60, .94),
                                   reader, FastStop(), log)
        self.assertEqual(result, PLAY_METHODS[1][0])
        client.direct_click.assert_called_once()
        client.direct_click_event.assert_called_once()
        client.direct_click_absolute.assert_not_called()

    def test_fail_all_methods_with_explanation(self):
        client, log = self.client(), Mock()
        reader = Mock()
        reader.read.return_value = []
        with self.assertRaisesRegex(RuntimeError, "None of the Play click methods"):
            test_play_methods(client, lambda f: (48, 60, .94),
                               reader, FastStop(), log)
        for _, method in PLAY_METHODS:
            getattr(client, method).assert_called_once()

    def test_cancel_after_click_never_tries_second_method(self):
        stop = FastStop()
        client = self.client()
        client.direct_click.side_effect = lambda *args: stop.set() or False
        result = test_play_methods(client, lambda f: (48, 60, 0.94),
                                   Mock(), stop, Mock())
        self.assertIsNone(result)
        client.direct_click_event.assert_not_called()

    def test_denied_focus_does_not_send_mouse_input(self):
        client = self.client()
        client.focus_roblox.side_effect = RuntimeError("Windows did not focus Roblox.")
        with self.assertRaisesRegex(RuntimeError, "focus"):
            test_play_methods(client, lambda f: (48, 60, .96),
                               Mock(), FastStop(), Mock())
        for _, method in PLAY_METHODS:
            getattr(client, method).assert_not_called()

    def test_reader_requires_unambiguous_story_text(self):
        reader = Mock()
        frame = np.zeros((90, 140, 4), dtype=np.uint8)
        reader.read.return_value = [match("Story"), match("Story")]
        self.assertFalse(story_visible(frame, reader))
        reader.read.return_value = [match("Story")]
        self.assertTrue(story_visible(frame, reader))
