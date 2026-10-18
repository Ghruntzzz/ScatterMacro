import unittest
from unittest.mock import Mock
from ctypes import wintypes

from python_macro.input import (
    RobloxClient, HOVER_SECONDS, JITTER_SECONDS, JITTER_OFFSETS,
    POST_JITTER_SECONDS, CLICK_HOLD_SECONDS,
    MOUSE_MOVE, MOUSE_ABSOLUTE, MOUSE_VIRTUAL_DESKTOP,
    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP,
    MOUSE_LEFT_DOWN, MOUSE_LEFT_UP, MOUSE_WHEEL, WHEEL_DELTA,
    INPUT, MOUSEINPUT, MAX_FOCUS_ATTEMPTS,
    PRECLICK_HOVER_SECONDS, PRECLICK_WIGGLE_SECONDS,
    PRECLICK_SETTLE_SECONDS, PRECLICK_WIGGLE_OFFSETS,
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


    def test_direct_click_hovers_wiggles_recenters_then_clicks(self):
        client = self.client()
        events = []
        old_move = client.user.SetCursorPos.side_effect
        client.user.SetCursorPos.side_effect = lambda x, y: (
            events.append(("pos", x, y)) or old_move(x, y)
        )
        client.stop.wait.side_effect = lambda duration: (
            events.append(("wait", duration)) or False
        )
        client.user.SendInput.side_effect = lambda n, packet, size: (
            events.append(("input", packet._obj.data.mi.dwFlags)) or 1
        )
        self.assertTrue(client.direct_click(20, 30, (80, 100, 4)))
        self.assertEqual(events[0:3], [
            ("pos", 20, 30), ("input", MOUSE_MOVE),
            ("wait", PRECLICK_HOVER_SECONDS),
        ])
        moves = [event for event in events if event[0] == "pos"]
        self.assertEqual(moves, [
            ("pos", 20, 30), ("pos", 17, 30), ("pos", 23, 30),
            ("pos", 20, 33), ("pos", 20, 27), ("pos", 20, 30),
            ("pos", 20, 30),
        ])
        self.assertEqual(
            [e[1] for e in events if e[0] == "input"],
            [MOUSE_MOVE] * (2 + len(PRECLICK_WIGGLE_OFFSETS)) +
            [MOUSE_LEFT_DOWN, MOUSE_LEFT_UP],
        )
        self.assertLess(events.index(("wait", PRECLICK_SETTLE_SECONDS)),
                        events.index(("input", MOUSE_LEFT_DOWN)))
        self.assertEqual(events[-2:], [("wait", CLICK_HOLD_SECONDS),
                                       ("input", MOUSE_LEFT_UP)])

    def test_direct_event_click_focuses_and_releases(self):
        client = self.client()
        client.focus_roblox = Mock(return_value=True)
        self.assertTrue(client.direct_click_event(20, 30, (80, 100, 4)))
        self.assertEqual([c.args[0] for c in client.user.mouse_event.call_args_list],
                         [MOUSE_LEFT_DOWN, MOUSE_LEFT_UP])
        self.assertTrue(all(c.args[1]._obj.data.mi.dwFlags == MOUSE_MOVE
                            for c in client.user.SendInput.call_args_list))

    def test_focus_restores_minimized_roblox_then_clicks(self):
        client = self.client()
        client.user.GetForegroundWindow.side_effect = [999, 123, 123, 123, 123]
        client.user.IsIconic.return_value = True
        self.assertTrue(client.direct_click(20, 30, (80, 100, 4)))
        client.user.ShowWindow.assert_called_once_with(123, 9)
        client.user.SetForegroundWindow.assert_called_once_with(123)
        self.assertEqual(
            [c.args[1]._obj.data.mi.dwFlags
             for c in client.user.SendInput.call_args_list[-2:]],
            [MOUSE_LEFT_DOWN, MOUSE_LEFT_UP],
        )

    def test_direct_click_never_sends_input_if_focus_denied(self):
        client = self.client()
        client.user.GetForegroundWindow.return_value = 456
        client.user.IsIconic.return_value = False
        with self.assertRaisesRegex(RuntimeError, "did not focus Roblox"):
            client.direct_click(20, 30, (80, 100, 4))
        self.assertEqual(client.user.SetForegroundWindow.call_count, MAX_FOCUS_ATTEMPTS)
        client.user.SendInput.assert_not_called()
        client.user.SetCursorPos.assert_not_called()

    def test_direct_click_stop_during_focus_prevents_input(self):
        client = self.client()
        client.user.GetForegroundWindow.return_value = 456
        client.user.IsIconic.return_value = False
        client.stop.wait.return_value = True
        self.assertFalse(client.direct_click(20, 30, (80, 100, 4)))
        client.user.SendInput.assert_not_called()

    def test_focus_skips_foreground_call_if_roblox_is_already_active(self):
        client = self.client()
        self.assertTrue(client.focus_roblox())
        client.user.SetForegroundWindow.assert_not_called()


    def test_all_four_methods_wait_to_settle_before_button_down(self):
        methods = ("direct_click", "direct_click_event",
                   "direct_click_absolute", "direct_click_message")
        for name in methods:
            with self.subTest(name=name):
                client = self.client()
                client.user.PostMessageW.return_value = True
                client.user.GetSystemMetrics.side_effect = lambda idx: {
                    76: 0, 77: 0, 78: 1920, 79: 1080,
                }[idx]
                events = []
                client.stop.wait.side_effect = lambda duration: (
                    events.append(("wait", duration)) or False
                )
                client.user.SendInput.side_effect = lambda n, pointer, size: (
                    events.append(("send", pointer._obj.data.mi.dwFlags)) or 1
                )
                client.user.mouse_event.side_effect = lambda flags, *a: (
                    events.append(("event", flags))
                )
                client.user.PostMessageW.side_effect = lambda hwnd, msg, *a: (
                    events.append(("post", msg)) or True
                )
                self.assertTrue(getattr(client, name)(20, 30, (80, 100, 4)))
                settle_index = events.index(("wait", PRECLICK_SETTLE_SECONDS))
                if name == "direct_click_event":
                    down = events.index(("event", MOUSE_LEFT_DOWN))
                elif name == "direct_click_message":
                    down = events.index(("post", WM_LBUTTONDOWN))
                else:
                    down = events.index(("send", MOUSE_LEFT_DOWN))
                self.assertLess(settle_index, down)
                self.assertGreaterEqual(
                    events.count(("wait", PRECLICK_WIGGLE_SECONDS)),
                    len(PRECLICK_WIGGLE_OFFSETS),
                )

    def test_stop_during_preclick_wiggle_never_presses_button(self):
        client = self.client()
        client.stop.wait.side_effect = [False, True]
        self.assertFalse(client.direct_click(20, 30, (80, 100, 4)))
        self.assertFalse(
            any(c.args[1]._obj.data.mi.dwFlags in (MOUSE_LEFT_DOWN, MOUSE_LEFT_UP)
                for c in client.user.SendInput.call_args_list)
        )

    def test_cursor_drift_after_settle_blocks_click(self):
        client = self.client()
        client.user.GetCursorPos.side_effect = lambda pointer: (
            setattr(pointer._obj, "x", 15) or
            setattr(pointer._obj, "y", 20) or True
        )
        with self.assertRaisesRegex(RuntimeError, "Cursor missed"):
            client.direct_click(20, 30, (80, 100, 4))
        self.assertFalse(
            any(c.args[1]._obj.data.mi.dwFlags in (MOUSE_LEFT_DOWN, MOUSE_LEFT_UP)
                for c in client.user.SendInput.call_args_list)
        )

    def test_hover_then_native_motion_jitter_then_checked_down_up(self):
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
            events.append(("send", pointer._obj.data.mi.dwFlags,
                           pointer._obj.data.mi.dx))
            return 1

        client.user.SendInput.side_effect = inject
        self.assertTrue(client.click(20, 30, (80, 100, 4)))
        self.assertEqual([x[1:] for x in events if x[0] == "move"],
                         [(20, 30), (18, 30), (22, 30), (20, 30), (20, 30)])
        injections = [x for x in events if x[0] == "send"]
        self.assertEqual(injections, [
            ("send", MOUSE_MOVE, 1), ("send", MOUSE_MOVE, -1),
            ("send", MOUSE_MOVE, 1), ("send", MOUSE_MOVE, -1),
            ("send", MOUSE_MOVE, 1), ("send", MOUSE_MOVE, -1),
            ("send", MOUSE_LEFT_DOWN, 0),
            ("send", MOUSE_LEFT_UP, 0),
        ])
        self.assertLess(events.index(("wait", HOVER_SECONDS)),
                        events.index(("send", MOUSE_MOVE, 1)))
        self.assertLess(events.index(("send", MOUSE_MOVE, -1)),
                        events.index(("send", MOUSE_LEFT_DOWN, 0)))
        self.assertIn(("wait", CLICK_HOLD_SECONDS), events)

    def test_ahk_event_fallback_preserves_hover_and_mouse_release(self):
        client = self.client()
        self.assertTrue(client.click_event(20, 30, (80, 100, 4)))
        self.assertEqual([call.args[0] for call in client.user.mouse_event.call_args_list],
                         [MOUSE_LEFT_DOWN, MOUSE_LEFT_UP])
        self.assertEqual(
            [c.args[1]._obj.data.mi.dwFlags for c in client.user.SendInput.call_args_list],
            [MOUSE_MOVE, MOUSE_MOVE] * len(JITTER_OFFSETS),
        )

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
        self.assertFalse(
            any(c.args[1]._obj.data.mi.dwFlags in (MOUSE_LEFT_DOWN, MOUSE_LEFT_UP)
                for c in client.user.SendInput.call_args_list)
        )

    def test_stop_during_mouse_down_still_releases(self):
        client = self.client()
        waits = [False] * (1 + len(JITTER_OFFSETS) + 1) + [True]
        client.stop.wait.side_effect = lambda _: waits.pop(0)
        client.stop.is_set.side_effect = lambda: not bool(waits)
        # Last false -> stop will flip only after click's hold.
        self.assertFalse(client.click(20, 30, (80, 100, 4)))
        self.assertEqual(
            [c.args[1]._obj.data.mi.dwFlags for c in client.user.SendInput.call_args_list
             if c.args[1]._obj.data.mi.dwFlags in (MOUSE_LEFT_DOWN, MOUSE_LEFT_UP)],
            [MOUSE_LEFT_DOWN, MOUSE_LEFT_UP],
        )

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
        self.assertFalse(
            any(c.args[1]._obj.data.mi.dwFlags in (MOUSE_LEFT_DOWN, MOUSE_LEFT_UP)
                for c in client.user.SendInput.call_args_list)
        )

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

    def test_absolute_click_normalizes_coordinates_and_releases(self):
        client = self.client()
        # Virtual desktop starting at (-100, -50) with two monitors.
        client.user.GetSystemMetrics.side_effect = lambda index: {
            76: -100, 77: -50, 78: 1600, 79: 1000,
        }[index]
        seen = []
        client.user.SendInput.side_effect = lambda n, p, s: (
            seen.append((p._obj.data.mi.dwFlags, p._obj.data.mi.dx,
                         p._obj.data.mi.dy)) or 1
        )
        self.assertTrue(client.direct_click_absolute(20, 30, (80, 100, 4)))
        self.assertEqual(seen[0][0], MOUSE_MOVE | MOUSE_ABSOLUTE | MOUSE_VIRTUAL_DESKTOP)
        self.assertEqual(seen[0][1], round(120 * 65535 / 1599))
        self.assertEqual(seen[0][2], round(80 * 65535 / 999))
        self.assertIn(MOUSE_MOVE, [s[0] for s in seen[1:-2]])
        self.assertEqual([s[0] for s in seen[-2:]], [MOUSE_LEFT_DOWN, MOUSE_LEFT_UP])

    def test_message_click_uses_client_coords_and_releases(self):
        client = self.client()
        client.user.PostMessageW.return_value = True
        self.assertTrue(client.direct_click_message(40, 50, (80, 100, 4)))
        sent = [c.args for c in client.user.PostMessageW.call_args_list]
        self.assertEqual([item[1] for item in sent],
                         [WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP])
        self.assertEqual([item[3] for item in sent], [((50 << 16) | 40)] * 3)
        self.assertTrue(all(c.args[1]._obj.data.mi.dwFlags == MOUSE_MOVE
                            for c in client.user.SendInput.call_args_list))

    def test_message_fail_down_does_not_falsely_succeed(self):
        client = self.client()
        client.user.PostMessageW.side_effect = [True, False]
        with self.assertRaisesRegex(RuntimeError, "button-down window message"):
            client.direct_click_message(40, 50, (80, 100, 4))
