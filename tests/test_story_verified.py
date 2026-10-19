import unittest
from threading import Event
from unittest.mock import Mock

import numpy as np

from python_macro.story_verified import click_and_confirm, click_once, changed_screen, FastText


class FastStop(Event):
    def wait(self, seconds=None):
        return self.is_set()


def frame(value=0):
    return np.full((80, 120, 4), value, dtype=np.uint8)


class VerifiedStoryTests(unittest.TestCase):
    def test_act_is_clicked_once_even_when_screen_does_not_change(self):
        capture = Mock(return_value=frame())
        click = Mock(return_value=True)
        locate = Mock(side_effect=[None, (25, 30)])
        self.assertTrue(click_once("Act 1", locate, capture, click, FastStop()))
        click.assert_called_once_with(25, 30, frame().shape)
        self.assertEqual(capture.call_count, 2)

    def test_act_does_not_retry_rejected_click(self):
        click = Mock(return_value=False)
        self.assertFalse(click_once("Act 1", lambda image: (25,30),
                                    lambda: frame(), click, FastStop()))
        click.assert_called_once()

    def test_act_stop_during_detection_prevents_click(self):
        stop, click = FastStop(), Mock()
        def locate(image):
            stop.set()
            return (25,30)
        self.assertFalse(click_once("Act 1", locate, lambda: frame(), click, stop))
        click.assert_not_called()

    def test_recovery_pass_can_stop_at_unique_expected_text(self):
        reader = Mock()
        reader.read.return_value = []
        ocr = FastText(reader, Event())
        ocr.scans = 4
        ocr.unique(frame(), lambda text: text == "Story")
        options = reader.read.call_args.kwargs
        self.assertEqual(options["max_variants"], 3)
        match = Mock(text="Story")
        self.assertTrue(options["accept"]([match]))
        self.assertFalse(options["accept"]([match, match]))
        self.assertFalse(options["accept"]([]))

    def test_click_retries_only_after_screen_fails_to_advance(self):
        state = {"clicks": 0, "new": False}
        targets = []
        def locate(image):
            x = 15 if state["clicks"] == 0 else 25
            targets.append(x)
            return x, 30
        def click(x, y, shape):
            state["clicks"] += 1
            if state["clicks"] == 2:
                state["new"] = True
            return True
        sent = []
        log = Mock()
        self.assertTrue(click_and_confirm(
            "Story", locate, lambda after, before: state["new"], lambda: frame(),
            click, FastStop(), log, highlight=lambda x, y, size: sent.append((x, y)),
            settle_seconds=0.0,
        ))
        self.assertEqual(state["clicks"], 2)
        self.assertEqual(sent, [(15, 30), (25, 30)])
        self.assertEqual(targets, [15, 25])
        log.assert_not_called()

    def test_stale_location_is_not_clicked(self):
        attempts = []
        def target(image):
            attempts.append(True)
            return (15, 30) if len(attempts) == 1 else None
        clicked = Mock(return_value=True)
        with self.assertRaisesRegex(RuntimeError, "Timed out"):
            click_and_confirm(
                "Start", target, lambda after, before: False, lambda: frame(),
                clicked, FastStop(), Mock(), timeout=0.03, settle_seconds=0.0,
            )
        self.assertEqual(clicked.call_count, 1)

    def test_rejected_sendinput_does_not_advance(self):
        clicked = Mock(return_value=False)
        success = click_and_confirm(
            "Play", lambda image: (15, 30), lambda after, before: True,
            lambda: frame(), clicked, FastStop(), Mock(), settle_seconds=0.0)
        self.assertFalse(success)
        clicked.assert_called_once()

    def test_stop_prevents_click(self):
        stop = FastStop()
        stop.set()
        click = Mock()
        self.assertFalse(click_and_confirm(
            "Play", lambda image: (15, 30), lambda after, before: False,
            lambda: frame(), click, stop, Mock()))
        click.assert_not_called()

    def test_no_advancement_has_bounded_retries(self):
        click = Mock(return_value=True)
        with self.assertRaisesRegex(RuntimeError, "Start did not respond"):
            click_and_confirm(
                "Start", lambda image: (15, 30), lambda after, before: False,
                lambda: frame(), click, FastStop(), Mock(), settle_seconds=0.0)
        self.assertEqual(click.call_count, 3)

    def test_scene_change_requires_substantial_pixel_change(self):
        a = frame()
        b = frame()
        b[0:40, :, :3] = 220
        self.assertTrue(changed_screen(a, b))
        c = frame()
        c[4:8, 4:8, :3] = 220
        self.assertFalse(changed_screen(a, c))

    def test_ocr_uses_fast_passes_with_periodic_fallback(self):
        reader = Mock()
        reader.read.return_value = []
        ocr = FastText(reader, FastStop())
        for i in range(5):
            ocr.unique(frame(i), lambda t: t == "Story")
        self.assertEqual([c.kwargs["scale"] for c in reader.read.call_args_list],
                         [1, 1, 1, 1, 2])
        self.assertEqual([c.kwargs["max_variants"] for c in reader.read.call_args_list],
                         [1, 1, 1, 1, 3])


if __name__ == "__main__":
    unittest.main()
