import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from concurrent.futures import Future
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication, QWidget
from ui.license_gate import open_gate


class SavedActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def check_restore(self, success):
        future = Future()
        executor = Mock()
        executor.submit.return_value = future
        heartbeat, polling = Mock(), Mock()
        loading = Mock()
        window = QWidget()
        factory = Mock(return_value=window)
        with patch('ui.license_gate.ThreadPoolExecutor', return_value=executor), \
             patch('ui.license_gate.QTimer', side_effect=[heartbeat, polling]), \
             patch('ui.license_gate.sys.argv', ['macro']):
            gate = open_gate(self.app, factory, '', loading=loading)
            try:
                self.assertFalse(gate.isVisible())
                factory.assert_not_called()
                loading.close.assert_not_called()
                if success:
                    future.set_result(Mock())
                else:
                    future.set_exception(ValueError('Activation required'))
                polling.timeout.connect.call_args.args[0]()
                self.assertEqual(gate.isVisible(), not success)
                loading.close.assert_called_once()
                if success:
                    factory.assert_called_once()
                    heartbeat.start.assert_called_once()
                else:
                    factory.assert_not_called()
                    self.assertTrue(gate.unlock.isEnabled())
            finally:
                gate.close()
                gate.deleteLater()
                window.close()
                window.deleteLater()

    def test_valid_saved_activation_never_shows_key_entry(self):
        self.check_restore(True)

    def test_failed_saved_activation_shows_key_entry_without_opening_macro(self):
        self.check_restore(False)
