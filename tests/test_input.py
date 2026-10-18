import unittest
from unittest.mock import Mock

from python_macro.input import (
    RobloxClient, HOVER_SECONDS, JITTER_SECONDS, JITTER_OFFSETS, WHEEL_DELTA,
)


class ClickTests(unittest.TestCase):
    def client(self):
        client = RobloxClient.__new__(RobloxClient)
        client.hwnd = 123
        client.stop = Mock()
        client.stop.is_set.return_value = False
        client.stop.wait.return_value = False
        client.user = Mock()
        client.user.GetForegroundWindow.return_value = 123
        client.user.GetAncestor.return_value = 123
        client.user.SetCursorPos.return_value = True

        def rect(hwnd, output):
            output._obj.right, output._obj.bottom = 100, 80
            return True

        client.user.GetClientRect.side_effect = rect
        client.user.ClientToScreen.return_value = True
        return client

    def test_hover_then_quick_jitter_then_mouse_down(self):
        client = self.client()
        events = []
        client.stop.wait.side_effect = lambda seconds: events.append(("wait", seconds)) or False
        client.user.SetCursorPos.side_effect = lambda x, y: events.append(("move", x, y)) or True
        client.user.mouse_event.side_effect = lambda flag, *args: events.append(("mouse", flag))
        client.click(20, 30, (80, 100, 4))
        self.assertEqual(events, [
            ("move", 20, 30), ("wait", HOVER_SECONDS),
            ("move", 18, 30), ("wait", JITTER_SECONDS),
            ("move", 22, 30), ("wait", JITTER_SECONDS),
            ("move", 20, 30), ("wait", JITTER_SECONDS),
            ("mouse", 2), ("wait", 0.05), ("mouse", 4),
        ])
        self.assertEqual(JITTER_OFFSETS[-1], (0, 0))

    def test_jitter_stays_inside_client_near_edges(self):
        client = self.client()
        moves = []
        client.user.SetCursorPos.side_effect = lambda x, y: moves.append((x, y)) or True
        client.click(0, 0, (80, 100, 4))
        self.assertTrue(all(0 <= x < 100 and 0 <= y < 80 for x, y in moves))
        self.assertEqual(moves[-1], (0, 0))

    def test_stop_during_hover_prevents_click(self):
        client = self.client()
        client.stop.wait.return_value = True
        client.click(20, 30, (80, 100, 4))
        client.user.mouse_event.assert_not_called()

    def test_stop_during_jitter_prevents_click(self):
        client = self.client()
        client.stop.wait.side_effect = [False, True]
        client.click(20, 30, (80, 100, 4))
        client.user.mouse_event.assert_not_called()

    def test_focus_loss_during_hover_prevents_click(self):
        client = self.client()
        client.user.GetForegroundWindow.side_effect = [123, 456]
        with self.assertRaises(RuntimeError):
            client.click(20, 30, (80, 100, 4))
        client.user.mouse_event.assert_not_called()

    def test_downward_wheel_is_sent_after_pointer_positioning(self):
        client = self.client()
        events = []
        client.user.SetCursorPos.side_effect = lambda x, y: events.append(("move", x, y)) or True
        client.user.mouse_event.side_effect = lambda flag, a, b, delta, e: events.append(("wheel", flag, delta))
        client.scroll(-2, 50, 67, (80, 100, 4))
        self.assertEqual(events[0], ("move", 50, 67))
        self.assertEqual(events[1][0:2], ("wheel", 0x0800))
        self.assertEqual(events[1][2] & 0xffffffff, (-2 * WHEEL_DELTA) & 0xffffffff)

    def test_stop_prevents_scrolling(self):
        client = self.client()
        client.stop.is_set.return_value = True
        client.scroll(-2, 50, 67, (80, 100, 4))
        client.user.mouse_event.assert_not_called()
