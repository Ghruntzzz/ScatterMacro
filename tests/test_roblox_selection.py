import unittest
from unittest.mock import patch

from python_macro.capture import selected_roblox_window


class RobloxSelectionTests(unittest.TestCase):
    def test_exact_hwnd_and_pid_required_with_multiple_windows(self):
        found = [(1001, "Roblox", 2001), (1002, "Roblox", 2002)]
        self.assertEqual(selected_roblox_window("1002", "2002", found), found[1])
        with self.assertRaisesRegex(RuntimeError, "Selected Roblox window"):
            selected_roblox_window("1001", "2002", found)
        with self.assertRaisesRegex(RuntimeError, "Selected Roblox window"):
            selected_roblox_window("1002", "2002", [found[0]])
        with self.assertRaisesRegex(RuntimeError, "Selected Roblox window"):
            selected_roblox_window("1002", "2002", [(1002, "Roblox", 9999)])

    def test_does_not_auto_switch_to_another_instance(self):
        with patch("python_macro.capture.roblox_windows",
                   return_value=[(900, "Roblox", 800)]):
            with self.assertRaises(RuntimeError):
                selected_roblox_window(100, 200)
