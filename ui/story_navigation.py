from threading import Event, Lock
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
    profile_changed = Signal(str,str,str,object)

    def __init__(self, map_name, parent, act_name="Act 1", difficulty="Normal",
                 selected_hwnd="", selected_pid="", reader=None, entries=(), reward_dir=None,
                 notification_settings=None, mode="Story"):
        super().__init__(parent)
        self.map_name = map_name
        self.act_name = act_name
        self.difficulty = difficulty
        self.mode = mode
        self.tower_type = map_name if mode=='Tower' else None
        self.selected_hwnd = selected_hwnd
        self.selected_pid = selected_pid
        self.stop = Event()
        self.reader = reader if reader is not None else TextReader()
        self.entries = [dict(entry) for entry in entries]
        self.entries_lock = Lock()
        self.reward_dir = reward_dir
        self.notification_settings = notification_settings or {}
        self.challenge_route = None

    def challenge_entries(self,map_name,act):
        return self.map_entries('Story',map_name,act)

    def map_entries(self,mode,map_name,act):
        from ui.dashboard import load_unit_indexes,active_unit_config
        values=dict(mode=mode,map=map_name,act=act)
        if mode=='Tower':
            values['tower_type']=self.tower_type
        path=active_unit_config(values)
        if path != self.challenge_route:
            entries=load_unit_indexes(values,count=len(self.entries))
            with self.entries_lock:
                self.entries=entries
                self.challenge_route=path
            self.profile_changed.emit(self.tower_type if mode=='Tower' else mode,map_name,act,[dict(e) for e in entries])
        return self.current_entries()

    def update_entry(self, index, entry):
        with self.entries_lock:
            self.entries[index] = dict(entry)

    def current_entries(self):
        with self.entries_lock:
            return [dict(entry) for entry in self.entries]

    def run(self):
        from python_macro.notifications import Notifier
        notifier = Notifier(self.notification_settings, self.stop, self.message.emit)
        def update_status(value):
            notifier.observe(value)
            self.hud_status.emit(value)
        try:
            from python_macro.capture import selected_roblox_window
            if self.selected_hwnd and self.selected_pid:
                target = selected_roblox_window(self.selected_hwnd, self.selected_pid)
            else:
                from python_macro.capture import single_roblox_window
                target = single_roblox_window()
            self.message.emit(f"Opening {self.mode} mode.")
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
            if self.mode=='Boss Rush':
                from python_macro.boss_rush import BossRushFlow,GateRoutes
                from ui.dashboard import active_unit_config
                from python_macro.capture import capture_client
                route_root=active_unit_config(dict(mode='Boss Rush',map='Gate map')).parent/'GateRoutes'
                flow=BossRushFlow(capture,client,self.reader,self.stop,self.message.emit,root/'assets',GateRoutes(route_root))
                def boss_capture():
                    if client.user.GetForegroundWindow()!=client.hwnd or client.user.IsIconic(client.hwnd):
                        return None
                    try:
                        return capture_client(client.hwnd)
                    except RuntimeError:
                        if client.user.GetForegroundWindow()!=client.hwnd or client.user.IsIconic(client.hwnd):
                            return None
                        raise
                def boss_profile(name):
                    self.map_entries('Boss Rush',name,'Gates')
                    notifier.settings.update(mode='Boss Rush',map=name,act='Gates',difficulty='')
                flow.run(play_icon,boss_profile,self.current_entries,update_status,boss_capture,self.reward_dir,notifier)
                return
            if self.mode == 'Expeditions':
                from python_macro.expeditions import ExpeditionFlow
                from python_macro.story_ingame import already_in_match,run_story_ingame
                from python_macro.capture import capture_client
                flow=ExpeditionFlow(capture,client,self.reader,self.stop,self.message.emit,
                                    root/'assets',self.map_name,self.difficulty,
                                    priority=self.notification_settings.get('card_priority',''))
                from python_macro.expedition_cards import anvil_order
                flow.cards.anvil_priority=anvil_order(self.notification_settings.get('anvil_priority',''))
                in_match=already_in_match(capture,self.reader,self.stop,self.map_name,
                                          'Expedition',self.difficulty,mode='Expedition')
                if not in_match and not flow.navigate(play_icon):
                    return
                def expedition_capture():
                    if client.user.GetForegroundWindow()!=client.hwnd or client.user.IsIconic(client.hwnd):
                        return None
                    try:
                        return capture_client(client.hwnd)
                    except RuntimeError:
                        if client.user.GetForegroundWindow()!=client.hwnd or client.user.IsIconic(client.hwnd):
                            return None
                        raise
                def expedition_profile(*args):
                    self.map_entries('Expeditions',self.map_name,'Expedition')
                if in_match:
                    expedition_profile()
                run_story_ingame(self.map_name,'Expedition',self.difficulty,capture,client,self.reader,
                                 self.stop,self.message.emit,root/'assets',self.entries,update_status,
                                 monitor_capture=expedition_capture,reward_dir=self.reward_dir,
                                 entries_provider=self.current_entries,match_confirmed=in_match,
                                 mode='Expedition',on_detect=expedition_profile,
                                 on_result=notifier.send,service=flow.service)
                return
            if self.mode == 'Tower':
                from python_macro.tower import TowerFlow
                from ui.dashboard import MODE_MAPS
                flow=TowerFlow(capture,client,self.reader,self.stop,self.message.emit,
                               root/'assets',self.tower_type)
                from python_macro.capture import capture_client
                def tower_capture():
                    if client.user.GetForegroundWindow()!=client.hwnd or client.user.IsIconic(client.hwnd):
                        return None
                    try:
                        return capture_client(client.hwnd)
                    except RuntimeError:
                        if client.user.GetForegroundWindow()!=client.hwnd or client.user.IsIconic(client.hwnd):
                            return None
                        raise
                def tower_map(map_name):
                    self.map_entries('Tower',map_name,'Floors')
                    notifier.settings.update(mode=self.tower_type,map=map_name,act='Floors',difficulty='')
                flow.run(play_icon,MODE_MAPS['Story'],tower_map,self.current_entries,update_status,
                         tower_capture,self.reward_dir,notifier,root/'assets')
                return
            if self.mode == 'Challenges':
                from python_macro.challenges import run_challenges
                from python_macro.capture import capture_client
                def challenge_capture():
                    if client.user.GetForegroundWindow() != client.hwnd or client.user.IsIconic(client.hwnd):
                        return None
                    try:
                        return capture_client(client.hwnd)
                    except RuntimeError:
                        if client.user.GetForegroundWindow() != client.hwnd or client.user.IsIconic(client.hwnd):
                            return None
                        raise
                run_challenges(capture,client,self.reader,self.stop,self.message.emit,root/'assets',
                               self.notification_settings,self.entries,update_status,challenge_capture,
                               self.reward_dir,self.current_entries,notifier,play_icon,
                               route_entries=self.challenge_entries)
                return
            from python_macro.story_ingame import already_in_match
            def detected(mode,map_name,act,difficulty):
                self.mode,self.map_name,self.act_name,self.difficulty=mode,map_name,act,difficulty
                notifier.settings.update(mode=mode,map=map_name,act=act,difficulty=difficulty)
                self.map_entries(mode,map_name,act)
            in_match = already_in_match(capture, self.reader, self.stop,
                                        self.map_name, self.act_name, self.difficulty,
                                        find_play=play_icon, mode=self.mode,on_detect=detected)
            if not in_match:
                navigate_story(self.map_name, capture, self.reader, client.direct_click,
                           self.stop, self.message.emit, scroll=client.scroll,
                           find_play=play_icon, act_name=self.act_name,
                           difficulty=self.difficulty, find_act=ActLabelLocator(),
                           find_start=StartButtonLocator(root / "assets" / "start-button-template.png"),
                           verify_clicks=True,
                           start_click=client.start_click,
                           find_story=StoryButtonLocator(root / "assets" / "story-button-template.png") if self.mode == 'Story' else None,
                           mode=self.mode,
                           highlight=lambda x, y, shape: self.click_target.emit(x, y))
            if not self.stop.is_set():
                from python_macro.story_ingame import run_story_ingame
                from python_macro.capture import capture_client
                def monitor_capture():
                    if client.user.GetForegroundWindow() != client.hwnd:
                        return None
                    try:
                        return capture_client(client.hwnd)
                    except RuntimeError:
                        if client.user.GetForegroundWindow() != client.hwnd or client.user.IsIconic(client.hwnd):
                            return None
                        raise
                run_story_ingame(self.map_name, self.act_name, self.difficulty,
                                 capture, client, self.reader, self.stop,
                                 self.message.emit, root / "assets", self.entries,
                                 update_status, monitor_capture=monitor_capture,
                                 reward_dir=self.reward_dir, entries_provider=self.current_entries,
                                 match_confirmed=in_match, on_result=notifier.send, mode=self.mode,
                                 on_detect=detected)
        except InterruptedError:
            self.stop.set()
        except Exception as exc:
            self.message.emit(f"Macro needs attention: {exc}")
            notifier.send('error')
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
