from threading import Event

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout

from python_macro.capture import roblox_windows
from python_macro.input import RobloxClient
from python_macro.ocr import TextReader
from python_macro.story import navigate_story


class StoryWorker(QThread):
    message = Signal(str)

    def __init__(self, map_name, parent):
        super().__init__(parent)
        self.map_name = map_name
        self.stop = Event()

    def run(self):
        try:
            windows = roblox_windows()
            if len(windows) != 1:
                raise RuntimeError("Open exactly one Roblox window before starting.")
            self.message.emit("Switch to Roblox. Navigation starts in 3 seconds.")
            if self.stop.wait(3):
                return
            client = RobloxClient(windows[0][0], self.stop)
            navigate_story(self.map_name, client.capture, TextReader(), client.click,
                           self.stop, self.message.emit)
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
