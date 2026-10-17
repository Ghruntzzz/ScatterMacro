import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
import tempfile
import time
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton
from ui.launcher import Launcher
from ui.loading import LoadingScreen
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from python_macro.library import Library, VERSION


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.window = Launcher(Library(self.folder.name))

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.folder.cleanup()

    def test_setup_macro_install_is_enabled(self):
        macro = self.window.catalog[0]
        self.assertTrue(macro["setup_only"])
        install = next(button for button in self.window.findChildren(QPushButton) if button.text() == "Install")
        self.assertTrue(install.isEnabled())

    def test_update_checks_never_open_windows_or_processes(self):
        self.window.show()
        baseline = {w for w in self.app.topLevelWidgets() if w.isVisible()}
        catalog = {"macros": self.window.catalog}
        release = {"version": VERSION, "url": "https://github.com/Ghruntz/ScatterMacro/releases/download/test/a.zip", "sha256": "0" * 64}
        with patch("ui.launcher.fetch_json", side_effect=[catalog, release]), \
             patch("ui.launcher.subprocess.Popen") as spawn, \
             patch.object(QMessageBox, "information") as info, \
             patch.object(QMessageBox, "question") as question:
            self.window.check_updates()
            deadline = time.monotonic() + 2
            while self.window.future is not None and time.monotonic() < deadline:
                self.app.processEvents()
                self.window.poll_job()
                self.assertEqual({w for w in self.app.topLevelWidgets() if w.isVisible()}, baseline)
                time.sleep(0.005)
            self.assertIsNone(self.window.future)
            spawn.assert_not_called()
            info.assert_not_called()
            question.assert_not_called()

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
