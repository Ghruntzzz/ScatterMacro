from pathlib import Path
from threading import Event
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from python_macro.chat import ChatLocator, ChatSafeCapture


class FastStop(Event):
    def wait(self, timeout=None):
        return self.is_set()


class ChatTests(unittest.TestCase):
    def test_reference_states_at_multiple_scales(self):
        assets = Path(__file__).resolve().parents[1] / "assets"
        locate = ChatLocator(assets)
        for state in ("open", "closed"):
            for scale in (1, 1.5, 2):
                with self.subTest(state=state, scale=scale):
                    icon = cv2.imread(str(assets / f"chat-{state}.png"))
                    icon = cv2.resize(icon, None, fx=scale, fy=scale)
                    frame = np.zeros((600, 900, 3), np.uint8)
                    h, w = icon.shape[:2]
                    frame[10:10+h, 100:100+w] = icon
                    self.assertEqual(locate(frame)[0], state)
        self.assertEqual(locate(np.zeros((600, 900, 3), np.uint8)), (None, None))

    def test_closed_chat_never_clicked(self):
        click = Mock()
        ChatSafeCapture(Mock(return_value=np.zeros((100,100,3))), click,
                        Mock(return_value=("closed", (20,20))), FastStop())()
        click.assert_not_called()

    def test_open_chat_clicked_once_and_closed_confirmed(self):
        click = Mock(return_value=True)
        stop = FastStop()
        locate = Mock(side_effect=[("open", (20,20)), ("closed", (20,20))])
        ChatSafeCapture(Mock(return_value=np.zeros((100,100,3))), click, locate, stop)()
        click.assert_called_once()
        self.assertFalse(stop.is_set())

    def test_failed_close_is_bounded(self):
        click = Mock(return_value=True)
        stop = FastStop()
        ChatSafeCapture(Mock(return_value=np.zeros((100,100,3))), click,
                        Mock(return_value=("open", (20,20))), stop)()
        self.assertEqual(click.call_count, 2)
        self.assertTrue(stop.is_set())

    def test_stop_prevents_click(self):
        stop = FastStop()
        stop.set()
        click = Mock()
        ChatSafeCapture(Mock(return_value=np.zeros((100,100,3))), click,
                        Mock(return_value=("open", (20,20))), stop)()
        click.assert_not_called()
