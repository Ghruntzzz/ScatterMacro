"""Window-scoped global F1/F2 registration, without keyboard hooks."""
import ctypes
from ctypes import wintypes


class RuntimeHotkeys:
    START, STOP = 0x5301, 0x5302

    def __init__(self, hwnd, user=None):
        self.hwnd = hwnd
        self.user = user if user is not None else ctypes.windll.user32
        if user is None:
            self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.registered = []

    def register(self):
        if self.registered:
            return
        for identifier, key in ((self.START, 0x70), (self.STOP, 0x71)):
            if not self.user.RegisterHotKey(self.hwnd, identifier, 0x4000, key):
                self.close()
                raise RuntimeError("F1/F2 are in use by another application. Close it and reopen the runtime.")
            self.registered.append(identifier)

    def close(self):
        for identifier in self.registered:
            self.user.UnregisterHotKey(self.hwnd, identifier)
        self.registered.clear()
