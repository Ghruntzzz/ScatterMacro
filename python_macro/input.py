"""Foreground-only client clicks with bounds and cancellation checks."""
import ctypes
from ctypes import wintypes


class RobloxClient:
    def __init__(self, hwnd, stop):
        self.hwnd, self.stop = hwnd, stop
        self.user = ctypes.windll.user32
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user.WindowFromPoint.argtypes = [wintypes.POINT]
        self.user.WindowFromPoint.restype = wintypes.HWND
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND

    def check_focus(self):
        if self.user.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("Keep Roblox in the foreground while navigation runs.")

    def capture(self):
        from python_macro.capture import capture_client
        self.check_focus()
        return capture_client(self.hwnd)

    def click(self, x, y, shape):
        if self.stop.is_set():
            return
        self.check_focus()
        rect = wintypes.RECT()
        if not self.user.GetClientRect(self.hwnd, ctypes.byref(rect)):
            raise RuntimeError("Roblox window is unavailable.")
        if (rect.bottom, rect.right) != shape[:2] or not (0 <= x < rect.right and 0 <= y < rect.bottom):
            raise RuntimeError("Roblox size changed. Restart navigation.")
        point = wintypes.POINT(x, y)
        if not self.user.ClientToScreen(self.hwnd, ctypes.byref(point)):
            raise RuntimeError("Cannot locate Roblox client.")
        target = self.user.WindowFromPoint(point)
        if self.user.GetAncestor(target, 2) != self.hwnd:
            raise RuntimeError("Another window is covering the detected button.")
        if not self.user.SetCursorPos(point.x, point.y):
            raise RuntimeError("Cannot move the cursor to Roblox.")
        self.check_focus()
        if self.stop.is_set():
            return
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        try:
            self.stop.wait(0.05)
        finally:
            self.user.mouse_event(0x0004, 0, 0, 0, 0)
