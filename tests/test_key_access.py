import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QPushButton
from python_macro.licensing import LicenseError, VerifiedLicense, verify_key
from ui.key_access import KeyAccess


class KeyAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
            self.window.deleteLater()
        self.app.processEvents()

    def make(self, verifier):
        self.window = KeyAccess("", verifier=verifier)
        self.accepted = Mock()
        self.window.unlocked.connect(self.accepted)
        return self.window

    def finish(self):
        deadline = time.monotonic() + 3
        while self.window.future is not None and time.monotonic() < deadline:
            self.app.processEvents()
            self.window.poll()
            time.sleep(0.005)
        self.assertIsNone(self.window.future)

    def test_empty_key_does_not_submit(self):
        verifier = Mock()
        self.make(verifier).submit()
        verifier.assert_not_called()
        self.accepted.assert_not_called()

    def test_rejection_and_network_failure_stay_locked(self):
        for error in (LicenseError("Invalid key"), OSError("private details")):
            with self.subTest(error=type(error)):
                if hasattr(self, "window"):
                    self.window.close()
                self.make(Mock(side_effect=error)).key.setText("secret")
                self.window.submit()
                self.finish()
                self.accepted.assert_not_called()
                self.assertTrue(self.window.unlock.isEnabled())
                self.assertNotIn("private details", self.window.status.text())

    def test_untyped_success_is_rejected(self):
        self.make(Mock(return_value=True)).key.setText("secret")
        self.window.submit()
        self.finish()
        self.accepted.assert_not_called()

    def test_verified_session_unlocks_once_and_clears_key(self):
        session = VerifiedLicense("test-session")
        verifier = Mock(return_value=session)
        self.make(verifier).key.setText(" secret ")
        self.window.submit()
        self.window.submit()
        self.finish()
        verifier.assert_called_once_with("secret")
        self.accepted.assert_called_once_with(session)
        self.assertEqual(self.window.key.text(), "")

    def test_links_open_correct_addresses(self):
        self.make(Mock())
        with patch("ui.key_access.QDesktopServices.openUrl", return_value=True) as opened:
            buttons = {button.text(): button for button in self.window.findChildren(QPushButton)}
            buttons["Get Key"].click()
            self.assertEqual(opened.call_args.args[0].toString(), "https://scatter-macro.shopscatter.workers.dev/dashboard")
            buttons["Discord"].click()
            self.assertEqual(opened.call_args.args[0].toString(), "https://discord.gg/VXAqRXvkKa")

    def test_incomplete_key_fails_closed(self):
        with self.assertRaises(LicenseError):
            verify_key("any-key")
