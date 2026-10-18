import unittest
from unittest.mock import Mock

from python_macro.input import RobloxClient, HOVER_SECONDS


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
        def rect(hwnd, output):
            output._obj.right, output._obj.bottom = 100, 80
            return True
        client.user.GetClientRect.side_effect = rect
        client.user.ClientToScreen.return_value = True
        return client

    def test_hover_precedes_mouse_down(self):
        client = self.client()
        events = []
        client.stop.wait.side_effect = lambda seconds: events.append(seconds) or False
        client.user.mouse_event.side_effect = lambda flag, *args: events.append(flag)
        client.click(20, 30, (80, 100, 4))
        self.assertEqual(events, [HOVER_SECONDS, 2, 0.05, 4])

    def test_stop_during_hover_prevents_click(self):
        client = self.client()
        client.stop.wait.return_value = True
        client.click(20, 30, (80, 100, 4))
        client.user.mouse_event.assert_not_called()

    def test_focus_loss_during_hover_prevents_click(self):
        client = self.client()
        client.user.GetForegroundWindow.side_effect = [123, 456]
        with self.assertRaises(RuntimeError):
            client.click(20, 30, (80, 100, 4))
        client.user.mouse_event.assert_not_called()
