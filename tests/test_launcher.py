import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton
from ui.launcher import Launcher
from ui.loading import LoadingScreen
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox


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
                       if button.text() == "Not released yet")
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

    def test_install_first_interface(self):
        texts = [button.text() for button in self.window.findChildren(QPushButton)]
        self.assertNotIn("Diagnostics", texts)
        self.assertNotIn("Preview dashboard", texts)
        self.assertNotIn("Project folder", texts)
        self.assertIn("Macro configs", texts)
        self.assertTrue(self.window.windowFlags() & Qt.FramelessWindowHint)

    def test_separate_update_controls(self):
        self.window.show_page("Updates")
        texts = [button.text() for button in self.window.findChildren(QPushButton)]
        self.assertIn("Check launcher updates", texts)
        self.assertIn("Check macro updates", texts)

    def test_open_checks_updates_before_launch(self):
        macro = self.window.catalog[0]
        latest = dict(macro, version="1.1.0")
        with patch.object(self.window.library, "installed", return_value={"version": "1.0.0"}), \
             patch.object(self.window, "start_job") as job, \
             patch.object(self.window, "launch_macro") as launch, \
             patch.object(self.window, "install_macro") as install, \
             patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.window.macro_action(macro)
            launch.assert_not_called()
            job.call_args.args[2]([latest])
            install.assert_called_once_with(latest, launch=True)
            launch.assert_not_called()

    def test_offline_launch_requires_confirmation(self):
        macro = self.window.catalog[0]
        with patch.object(self.window.library, "installed", return_value={"version": "1.0.0"}), \
             patch.object(self.window, "start_job") as job, \
             patch.object(self.window, "launch_macro") as launch, \
             patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.window.macro_action(macro)
            job.call_args.args[3](OSError("offline"))
            launch.assert_not_called()
