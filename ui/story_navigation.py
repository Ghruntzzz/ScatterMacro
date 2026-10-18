from threading import Event
from pathlib import Path
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout

from python_macro.capture import roblox_windows
from python_macro.input import RobloxClient
from python_macro.ocr import TextReader
from python_macro.story import navigate_story
from python_macro.vision import PlayIconLocator


class StoryWorker(QThread):
    message = Signal(str)

    def __init__(self, map_name, parent, act_name="Act 1", difficulty="Normal"):
        super().__init__(parent)
        self.map_name = map_name
        self.act_name = act_name
        self.difficulty = difficulty
        self.stop = Event()

    def run(self):
        try:
            windows = roblox_windows()
            if len(windows) != 1:
                raise RuntimeError("Open exactly one Roblox window before starting.")
            self.message.emit("Opening Story mode.")
            if self.stop.wait(0.5):
                return
            client = RobloxClient(windows[0][0], self.stop)
            if not client.focus_roblox():
                return
            root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
            play_icon = PlayIconLocator(root / "assets" / "play-button-template.png")
            navigate_story(self.map_name, client.capture, TextReader(), client.direct_click,
                           self.stop, self.message.emit, scroll=client.scroll,
                           find_play=play_icon, act_name=self.act_name,
                           difficulty=self.difficulty)
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
