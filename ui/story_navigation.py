from threading import Event
from pathlib import Path
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout

from python_macro.capture import roblox_windows
from python_macro.input import RobloxClient
from python_macro.click_diagnostics import test_play_methods
from python_macro.ocr import TextReader
from python_macro.story import navigate_story
from python_macro.vision import PlayIconLocator


class StoryWorker(QThread):
    message = Signal(str)

    def __init__(self, map_name, parent, test_only=False):
        super().__init__(parent)
        self.map_name = map_name
        self.test_only = test_only
        self.stop = Event()

    def run(self):
        try:
            windows = roblox_windows()
            if len(windows) != 1:
                raise RuntimeError("Open exactly one Roblox window before starting.")
            self.message.emit("Focusing Roblox for direct clicks.")
            if self.stop.wait(0.5):
                return
            client = RobloxClient(windows[0][0], self.stop)
            if not client.focus_roblox():
                return
            self.message.emit("Roblox is focused. Starting Story navigation.")
            root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
            play_icon = PlayIconLocator(root / "assets" / "play-button-template.png")
            reader = TextReader()
            method = test_play_methods(client, play_icon, reader, self.stop,
                                       self.message.emit)
            if self.stop.is_set() or method is None:
                return
            if self.test_only:
                self.message.emit(f"Click test finished. Working method: {method}.")
                return
            self.message.emit(f"Continuing Story navigation after {method}.")
            navigate_story(self.map_name, client.capture, reader, client.direct_click,
                           self.stop, self.message.emit, scroll=client.scroll,
                           find_play=None, skip_play=True)
        except Exception as exc:
            self.message.emit(f"Navigation stopped: {exc}")
        finally:
            if self.stop.is_set():
                self.message.emit("Macro stopped.")


class StoryNavigationDialog(QDialog):
    def __init__(self, map_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Story navigation")
        self.resize(520, 300)
        layout = QVBoxLayout(self)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        self.button = QPushButton("Stop")
        layout.addWidget(self.button)
        self.worker = StoryWorker(map_name, self)
        self.worker.message.connect(self.output.appendPlainText)
        self.worker.finished.connect(lambda: self.button.setText("Close"))
        self.button.clicked.connect(self.reject)
        self.worker.start()

    def reject(self):
        if self.worker.isRunning():
            self.worker.stop.set()
            self.button.setText("Stopping...")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.stop.set()
            event.ignore()
        else:
            super().closeEvent(event)
