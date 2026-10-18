import unittest
from unittest.mock import Mock
from ctypes import wintypes

from python_macro.input import (
    RobloxClient, HOVER_SECONDS, JITTER_SECONDS, JITTER_OFFSETS,
    POST_JITTER_SECONDS, CLICK_HOLD_SECONDS,
    MOUSE_LEFT_DOWN, MOUSE_LEFT_UP, MOUSE_WHEEL, WHEEL_DELTA,
    INPUT, MOUSEINPUT,
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
        client.user.GetCursorPos.return_value = True
        client.user.SendInput.return_value = 1
        cursor = [0, 0]

        def move(x, y):
            cursor[:] = [x, y]
            return True

        def get_cursor(output):
            output._obj.x, output._obj.y = cursor
            return True

        def rect(hwnd, output):
            output._obj.right, output._obj.bottom = 100, 80
            return True

        client.user.SetCursorPos.side_effect = move
        client.user.GetCursorPos.side_effect = get_cursor
        client.user.GetClientRect.side_effect = rect
        client.user.ClientToScreen.return_value = True
        return client

    def test_hover_then_jitter_then_checked_down_up(self):
        client = self.client()
        events = []
        client.stop.wait.side_effect = lambda s: events.append(("wait", s)) or False
        old_move = client.user.SetCursorPos.side_effect

        def move(x, y):
            events.append(("move", x, y))
            return old_move(x, y)

        client.user.SetCursorPos.side_effect = move

        def inject(count, pointer, size):
            self.assertEqual(count, 1)
            self.assertEqual(size, __import__("ctypes").sizeof(INPUT))
            events.append(("send", pointer._obj.data.mi.dwFlags))
            return 1

        client.user.SendInput.side_effect = inject
        self.assertTrue(client.click(20, 30, (80, 100, 4)))
        self.assertEqual(events, [
            ("move", 20, 30), ("wait", HOVER_SECONDS),
            ("move", 18, 30), ("wait", JITTER_SECONDS),
            ("move", 22, 30), ("wait", JITTER_SECONDS),
            ("move", 20, 30), ("wait", JITTER_SECONDS),
            ("wait", POST_JITTER_SECONDS),
            ("send", MOUSE_LEFT_DOWN), ("wait", CLICK_HOLD_SECONDS),
            ("send", MOUSE_LEFT_UP),
        ])

    def test_jitter_stays_inside_client_near_edges(self):
        client = self.client()
        self.assertTrue(client.click(0, 0, (80, 100, 4)))
        moves = [c.args for c in client.user.SetCursorPos.call_args_list]
        self.assertTrue(all(0 <= x < 100 and 0 <= y < 80 for x, y in moves))
        self.assertEqual(moves[-1], (0, 0))

    def test_stop_during_hover_prevents_input(self):
        client = self.client()
        client.stop.wait.return_value = True
        self.assertFalse(client.click(20, 30, (80, 100, 4)))
        client.user.SendInput.assert_not_called()

    def test_stop_during_jitter_prevents_input(self):
        client = self.client()
        client.stop.wait.side_effect = [False, True]
        self.assertFalse(client.click(20, 30, (80, 100, 4)))
        client.user.SendInput.assert_not_called()

    def test_stop_during_mouse_down_still_releases(self):
        client = self.client()
        waits = [False] * (1 + len(JITTER_OFFSETS) + 1) + [True]
        client.stop.wait.side_effect = lambda _: waits.pop(0)
        client.stop.is_set.side_effect = lambda: not bool(waits)
        # Last false -> stop will flip only after click's hold.
        self.assertFalse(client.click(20, 30, (80, 100, 4)))
        self.assertEqual(client.user.SendInput.call_count, 2)

    def test_focus_loss_prevents_input(self):
        client = self.client()
        client.user.GetForegroundWindow.side_effect = [123, 456]
        with self.assertRaises(RuntimeError):
            client.click(20, 30, (80, 100, 4))
        client.user.SendInput.assert_not_called()

    def test_rejected_injection_raises_instead_of_claiming_click(self):
        client = self.client()
        client.user.SendInput.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "rejected mouse input"):
            client.click(20, 30, (80, 100, 4))

    def test_wrong_cursor_position_prevents_input(self):
        client = self.client()
        client.user.GetCursorPos.side_effect = lambda point: (
            setattr(point._obj, "x", 99) or
            setattr(point._obj, "y", 50) or True
        )
        with self.assertRaisesRegex(RuntimeError, "Cursor missed"):
            client.click(20, 30, (80, 100, 4))
        client.user.SendInput.assert_not_called()

    def test_downward_scroll_uses_checked_input(self):
        client = self.client()
        data = []

        def record(count, packet, size):
            data.append((packet._obj.data.mi.dwFlags, packet._obj.data.mi.mouseData))
            return 1

        client.user.SendInput.side_effect = record
        client.scroll(-2, 50, 67, (80, 100, 4))
        self.assertEqual(data, [(MOUSE_WHEEL, (-2 * WHEEL_DELTA) & 0xffffffff)])

    def test_cancel_prevents_scroll(self):
        client = self.client()
        client.stop.is_set.return_value = True
        client.scroll(-2, 50, 67, (80, 100, 4))
        client.user.SendInput.assert_not_called()
