import unittest
from unittest.mock import Mock, call

from python_macro.hotkeys import RuntimeHotkeys


class HotkeyTests(unittest.TestCase):
    def test_registration_and_cleanup(self):
        user = Mock()
        keys = RuntimeHotkeys(123, user)
        keys.register()
        keys.register()
        self.assertEqual(user.RegisterHotKey.call_args_list,
                         [call(123, keys.START, 0x4000, 0x70), call(123, keys.STOP, 0x4000, 0x71)])
        keys.close()
        keys.close()
        self.assertEqual(user.UnregisterHotKey.call_count, 2)

    def test_conflict_rolls_back_start(self):
        user = Mock()
        user.RegisterHotKey.side_effect = [True, False]
        keys = RuntimeHotkeys(123, user)
        with self.assertRaises(RuntimeError):
            keys.register()
        user.UnregisterHotKey.assert_called_once_with(123, keys.START)
        self.assertEqual(keys.registered, [])
