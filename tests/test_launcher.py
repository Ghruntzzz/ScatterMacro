import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton
from ui.launcher import Launcher
from ui.loading import LoadingScreen


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = Launcher()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_unreleased_macro_cannot_be_installed(self):
        install = next(button for button in self.window.findChildren(QPushButton)
                       if button.text() == "Install available after release")
        self.assertFalse(install.isEnabled())

    def test_loading_screen_closes_when_launcher_ready(self):
        splash = LoadingScreen("")
        splash.show()
        self.app.processEvents()
        self.assertTrue(splash.isVisible())
        splash.finish(self.window)
        self.assertFalse(splash.isVisible())
        self.assertTrue(self.window.isVisible())
        splash.deleteLater()

    def test_search_and_navigation(self):
        search = self.window.findChild(QLineEdit)
        search.setText("nonexistent game")
        empty = next(label for label in self.window.findChildren(QLabel)
                     if label.text() == "No matching macros.")
        self.assertFalse(empty.isHidden())
        search.setText("anime")
        self.assertTrue(empty.isHidden())
        for page in ("Installed", "Updates", "Home"):
            self.window.show_page(page)
            self.assertTrue(self.window.nav[page].isChecked())

    def test_diagnostics_without_roblox_never_captures(self):
        with patch("python_macro.capture.roblox_windows", return_value=[]), \
             patch("python_macro.capture.capture_client") as capture:
            self.window.show_page("Diagnostics")
            button = next(button for button in self.window.findChildren(QPushButton)
                          if button.text() == "Capture client")
            self.assertFalse(button.isEnabled())
            capture.assert_not_called()
