from threading import Event
from pathlib import Path
import sys

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from python_macro.capture import roblox_windows
from python_macro.input import RobloxClient
from python_macro.ocr import TextReader
from python_macro.story import navigate_story
from python_macro.vision import PlayIconLocator, StartButtonLocator, StoryButtonLocator
from python_macro.act_labels import ActLabelLocator


class StoryWorker(QThread):
    message = Signal(str)
    click_target = Signal(int, int)
    hud_status = Signal(object)

    def __init__(self, map_name, parent, act_name="Act 1", difficulty="Normal",
                 selected_hwnd="", selected_pid="", reader=None, entries=()):
        super().__init__(parent)
        self.map_name = map_name
        self.act_name = act_name
        self.difficulty = difficulty
        self.selected_hwnd = selected_hwnd
        self.selected_pid = selected_pid
        self.stop = Event()
        self.reader = reader if reader is not None else TextReader()
        self.entries = [dict(entry) for entry in entries]

    def run(self):
        try:
            from python_macro.capture import selected_roblox_window
            if self.selected_hwnd and self.selected_pid:
                target = selected_roblox_window(self.selected_hwnd, self.selected_pid)
            else:
                from python_macro.capture import single_roblox_window
                target = single_roblox_window()
            self.message.emit("Opening Story mode.")
            if self.stop.wait(0.5):
                return
            client = RobloxClient(target[0], self.stop, selected_pid=target[2])
            if not client.focus_roblox():
                return
            root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
            play_icon = PlayIconLocator(root / "assets" / "play-button-template.png")
            from python_macro.chat import ChatLocator, ChatSafeCapture
            capture = ChatSafeCapture(client.capture, client.direct_click,
                                      ChatLocator(root / "assets"), self.stop)
            navigate_story(self.map_name, capture, self.reader, client.direct_click,
                           self.stop, self.message.emit, scroll=client.scroll,
                           find_play=play_icon, act_name=self.act_name,
                           difficulty=self.difficulty, find_act=ActLabelLocator(),
                           find_start=StartButtonLocator(root / "assets" / "start-button-template.png"),
                           verify_clicks=True,
                           start_click=client.start_click,
                           find_story=StoryButtonLocator(root / "assets" / "story-button-template.png"),
                           highlight=lambda x, y, shape: self.click_target.emit(x, y))
            if not self.stop.is_set():
                from python_macro.story_ingame import run_story_ingame
                run_story_ingame(self.map_name, self.act_name, self.difficulty,
                                 capture, client, self.reader, self.stop,
                                 self.message.emit, root / "assets", self.entries,
                                 self.hud_status.emit)
        except InterruptedError:
            self.stop.set()
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


class ClickTargetOverlay(QWidget):
    """Non-activating, mouse-transparent ring drawn over the intended click."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(54, 54)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_at(self, x, y):
        # WS_EX_TRANSPARENT makes the Win32 overlay click-through too.
        if sys.platform == "win32":
            import ctypes
            hwnd = int(self.winId())
            user = ctypes.windll.user32
            get_style = user.GetWindowLongPtrW
            set_style = user.SetWindowLongPtrW
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_style.restype = ctypes.c_ssize_t
            style = get_style(hwnd, -20)
            set_style(hwnd, -20, style | 0x20 | 0x80000 | 0x08000000)
        self.move(int(x) - 27, int(y) - 27)
        self.show()
        self.raise_()
        self.timer.start(750)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#ffdf4d"), 3))
        painter.drawEllipse(8, 8, 38, 38)
        painter.drawLine(27, 0, 27, 14)
        painter.drawLine(27, 40, 27, 53)
        painter.drawLine(0, 27, 14, 27)
        painter.drawLine(40, 27, 53, 27)
        painter.setBrush(QColor("#ffdf4d"))
        painter.drawEllipse(24, 24, 6, 6)
