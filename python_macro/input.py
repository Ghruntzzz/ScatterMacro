"""Foreground-only client input with hover, tiny pre-click jitter and safe scrolling."""
import ctypes
from ctypes import wintypes

HOVER_SECONDS = 0.25
JITTER_SECONDS = 0.012
JITTER_OFFSETS = ((-2, 0), (2, 0), (0, 0))
WHEEL_DELTA = 120


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

    def _validated_point(self, x, y, shape):
        self.check_focus()
        rect = wintypes.RECT()
        if not self.user.GetClientRect(self.hwnd, ctypes.byref(rect)):
            raise RuntimeError("Roblox window is unavailable.")
        if (rect.bottom, rect.right) != shape[:2] or not (0 <= x < rect.right and 0 <= y < rect.bottom):
            raise RuntimeError("Roblox size changed. Restart navigation.")
        point = wintypes.POINT(x, y)
        if not self.user.ClientToScreen(self.hwnd, ctypes.byref(point)):
            raise RuntimeError("Cannot locate Roblox client.")
        if self.user.GetAncestor(self.user.WindowFromPoint(point), 2) != self.hwnd:
            raise RuntimeError("Another window is covering the detected target.")
        return point, rect

    def _move(self, x, y):
        point = wintypes.POINT(x, y)
        if self.user.GetAncestor(self.user.WindowFromPoint(point), 2) != self.hwnd:
            raise RuntimeError("The target was covered during cursor movement.")
        if not self.user.SetCursorPos(x, y):
            raise RuntimeError("Cannot move the cursor to Roblox.")

    def click(self, x, y, shape):
        if self.stop.is_set():
            return
        point, rect = self._validated_point(x, y, shape)
        self._move(point.x, point.y)
        if self.stop.wait(HOVER_SECONDS):
            return
        current, _ = self._validated_point(x, y, shape)
        if (current.x, current.y) != (point.x, point.y):
            raise RuntimeError("Roblox moved during hover. Restart navigation.")
        # Small, fast motion happens AFTER hovering, BEFORE pressing the mouse.
        for dx, dy in JITTER_OFFSETS:
            if self.stop.is_set():
                return
            self.check_focus()
            self._move(point.x + max(-x, min(dx, rect.right - 1 - x)),
                       point.y + max(-y, min(dy, rect.bottom - 1 - y)))
            if self.stop.wait(JITTER_SECONDS):
                return
        final, _ = self._validated_point(x, y, shape)
        if (final.x, final.y) != (point.x, point.y):
            raise RuntimeError("Roblox moved before clicking. Restart navigation.")
        if self.stop.is_set():
            return
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        try:
            self.stop.wait(0.05)
        finally:
            self.user.mouse_event(0x0004, 0, 0, 0, 0)

    def scroll(self, steps, x, y, shape):
        """Scroll at a verified Roblox client point; negative steps scroll down."""
        if self.stop.is_set() or not steps:
            return
        point, _ = self._validated_point(x, y, shape)
        self._move(point.x, point.y)
        self.check_focus()
        if self.stop.is_set():
            return
        self.user.mouse_event(0x0800, 0, 0,
                              ctypes.c_ulong(int(steps) * WHEEL_DELTA).value, 0)
