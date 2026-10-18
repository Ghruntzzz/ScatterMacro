"""Foreground-only Win32 input with a confirmed cursor and checked mouse injection."""
import ctypes
from ctypes import wintypes

HOVER_SECONDS = 0.25
JITTER_SECONDS = 0.012
JITTER_OFFSETS = ((-2, 0), (2, 0), (0, 0))
POST_JITTER_SECONDS = 0.045
CLICK_HOLD_SECONDS = 0.12
WHEEL_DELTA = 120

MOUSE_LEFT_DOWN = 0x0002
MOUSE_LEFT_UP = 0x0004
MOUSE_WHEEL = 0x0800
INPUT_MOUSE = 0


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", INPUT_UNION)]


class RobloxClient:
    def __init__(self, hwnd, stop):
        self.hwnd, self.stop = hwnd, stop
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user.WindowFromPoint.argtypes = [wintypes.POINT]
        self.user.WindowFromPoint.restype = wintypes.HWND
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user.GetCursorPos.restype = wintypes.BOOL
        self.user.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user.SetCursorPos.restype = wintypes.BOOL
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user.SendInput.restype = wintypes.UINT

    def check_focus(self):
        if self.user.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("Roblox lost focus. Bring Roblox forward and try again.")

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
            raise RuntimeError("Another window covers the Play button. Keep Roblox visible.")
        return point, rect

    def _move(self, x, y):
        point = wintypes.POINT(x, y)
        if self.user.GetAncestor(self.user.WindowFromPoint(point), 2) != self.hwnd:
            raise RuntimeError("The Roblox click target is covered.")
        if not self.user.SetCursorPos(x, y):
            raise RuntimeError("Windows could not position the mouse cursor.")

    def _check_cursor(self, x, y):
        actual = wintypes.POINT()
        if not self.user.GetCursorPos(ctypes.byref(actual)):
            raise RuntimeError("Windows could not verify the cursor location.")
        if (actual.x, actual.y) != (x, y):
            raise RuntimeError(
                f"Cursor missed the target: expected ({x}, {y}), "
                f"actual ({actual.x}, {actual.y}). Check Windows scaling."
            )

    def _send_mouse(self, flags, data=0):
        # Unlike legacy mouse_event, SendInput returns the number of accepted
        # inputs. A zero return is a transport failure, not a successful click.
        packet = INPUT(type=INPUT_MOUSE,
                       data=INPUT_UNION(mi=MOUSEINPUT(
                           dx=0, dy=0,
                           mouseData=data & 0xffffffff,
                           dwFlags=flags, time=0, dwExtraInfo=0,
                       )))
        count = self.user.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT))
        if count != 1:
            error = ctypes.get_last_error()
            raise RuntimeError(
                f"Windows rejected mouse input (SendInput={count}, error={error}). "
                "Check Roblox focus, overlays, and whether Roblox runs as administrator."
            )

    def click(self, x, y, shape):
        if self.stop.is_set():
            return False
        point, rect = self._validated_point(x, y, shape)
        self._move(point.x, point.y)
        if self.stop.wait(HOVER_SECONDS):
            return False
        current, _ = self._validated_point(x, y, shape)
        if (current.x, current.y) != (point.x, point.y):
            raise RuntimeError("Roblox moved during hover. Restart navigation.")
        for dx, dy in JITTER_OFFSETS:
            if self.stop.is_set():
                return False
            self.check_focus()
            self._move(
                point.x + max(-x, min(dx, rect.right - 1 - x)),
                point.y + max(-y, min(dy, rect.bottom - 1 - y)),
            )
            if self.stop.wait(JITTER_SECONDS):
                return False
        if self.stop.wait(POST_JITTER_SECONDS):
            return False
        final, _ = self._validated_point(x, y, shape)
        if (final.x, final.y) != (point.x, point.y):
            raise RuntimeError("Roblox moved before clicking. Restart navigation.")
        self._check_cursor(point.x, point.y)
        if self.stop.is_set():
            return False
        self._send_mouse(MOUSE_LEFT_DOWN)
        try:
            self.stop.wait(CLICK_HOLD_SECONDS)
        finally:
            # Always release even if F2 stops the macro during the click.
            self._send_mouse(MOUSE_LEFT_UP)
        return not self.stop.is_set()

    def scroll(self, steps, x, y, shape):
        if self.stop.is_set() or not steps:
            return
        point, _ = self._validated_point(x, y, shape)
        self._move(point.x, point.y)
        self._check_cursor(point.x, point.y)
        self.check_focus()
        if self.stop.is_set():
            return
        self._send_mouse(MOUSE_WHEEL, int(steps) * WHEEL_DELTA)
