"""Foreground-filtered WASD recording with F3 to finish."""
from PySide6.QtCore import QObject,QTimer,Signal
from python_macro.pathing import PathRecording


class PathRecorder(QObject):
    finished=Signal(str)
    failed=Signal(str)

    def __init__(self,client,window):
        super().__init__(window)
        self.client=client
        self.recording=None
        self.active=False
        self.timer=QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.sample)

    def start(self):
        try:
            if not self.client.focus_roblox():
                raise RuntimeError('Could not focus Roblox.')
            self.recording=PathRecording()
            self.active=True
            self.sample()
            if self.active:
                self.timer.start()
        except Exception:
            self.cleanup()
            raise

    def sample(self):
        if not self.active:
            return
        user=self.client.user
        if user.GetAsyncKeyState(0x72)&0x8000:  # F3, irrespective of foreground.
            self.finish()
            return
        focused=user.GetForegroundWindow()==self.client.hwnd
        keys=[key for key in 'WASD' if focused and user.GetAsyncKeyState(ord(key))&0x8000]
        if not self.recording.sample(focused,keys):
            self.finish()

    def cleanup(self):
        self.active=False
        self.timer.stop()

    def finish(self):
        if not self.active:
            return
        self.cleanup()
        try:
            self.finished.emit(self.recording.finish())
        except ValueError as error:
            self.failed.emit(str(error))
