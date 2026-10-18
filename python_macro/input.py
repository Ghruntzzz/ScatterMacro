"""Foreground-only Win32 input with a confirmed cursor and checked mouse injection."""
import ctypes
from ctypes import wintypes

HOVER_SECONDS = 0.25
JITTER_SECONDS = 0.012
JITTER_OFFSETS = ((-2, 0), (2, 0), (0, 0))
POST_JITTER_SECONDS = 0.045
CLICK_HOLD_SECONDS = 0.12
FOCUS_SETTLE_SECONDS = 0.10
MAX_FOCUS_ATTEMPTS = 3
PRECLICK_HOVER_SECONDS = 0.18
PRECLICK_WIGGLE_SECONDS = 0.035
PRECLICK_SETTLE_SECONDS = 0.13
PRECLICK_WIGGLE_OFFSETS = ((-3, 0), (3, 0), (0, 3), (0, -3), (0, 0))
WHEEL_DELTA = 120

MOUSE_MOVE = 0x0001
MOUSE_ABSOLUTE = 0x8000
MOUSE_VIRTUAL_DESKTOP = 0x4000
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
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
        self.user.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                         wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        self.user.mouse_event.restype = None
        self.user.IsIconic.argtypes = [wintypes.HWND]
        self.user.IsIconic.restype = wintypes.BOOL
        self.user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.ShowWindow.restype = wintypes.BOOL
        self.user.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user.SetForegroundWindow.restype = wintypes.BOOL
        self.user.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user.GetSystemMetrics.restype = ctypes.c_int
        self.user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.PostMessageW.restype = wintypes.BOOL

    def check_focus(self):
        if self.user.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("Roblox lost focus. Bring Roblox forward and try again.")

    def focus_roblox(self):
        """Request real foreground focus and verify it before sending input.

        Windows can deny SetForegroundWindow because of foreground-lock rules.
        If that happens, never click a different window.
        """
        if self.stop.is_set():
            return False
        if self.user.GetForegroundWindow() == self.hwnd:
            return True
        if self.user.IsIconic(self.hwnd):
            self.user.ShowWindow(self.hwnd, 9)  # SW_RESTORE
        for _ in range(MAX_FOCUS_ATTEMPTS):
            if self.stop.is_set():
                return False
            self.user.SetForegroundWindow(self.hwnd)
            if self.stop.wait(FOCUS_SETTLE_SECONDS):
                return False
            if self.user.GetForegroundWindow() == self.hwnd:
                return True
        raise RuntimeError(
            "Windows did not focus Roblox. Click the Roblox window once, "
            "then start the macro again. No input was sent."
        )

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

    def _send_mouse(self, flags, data=0, dx=0, dy=0):
        # Unlike legacy mouse_event, SendInput returns the number of accepted
        # inputs. A zero return is a transport failure, not a successful click.
        packet = INPUT(type=INPUT_MOUSE,
                       data=INPUT_UNION(mi=MOUSEINPUT(
                           dx=dx, dy=dy,
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
        return self._click(x, y, shape, method="input")

    def click_event(self, x, y, shape):
        """AHK SendMode Event-like attempt when SendInput did not change the menu."""
        return self._click(x, y, shape, method="event")

    def direct_click(self, x, y, shape):
        """Focus Roblox and click the target immediately without hover/jitter."""
        return self._direct_click(x, y, shape, method="input")

    def direct_click_event(self, x, y, shape):
        """Direct AHK-style Event fallback, also without hover/jitter."""
        return self._direct_click(x, y, shape, method="event")

    def _prepare_click_target(self, x, y, shape, absolute=False):
        """Hover, inject actual mouse-motion wiggle, then settle on target.

        A moved visible cursor does not prove that a game has processed the
        pointer's new location. Emit native MOUSE_MOVE events BEFORE button
        down, wait for dispatch, and revalidate both position and foreground.
        """
        if not self.focus_roblox():
            return None
        point, rect = self._validated_point(x, y, shape)
        if absolute:
            left = self.user.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            top = self.user.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            width = self.user.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            height = self.user.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if width < 2 or height < 2:
                raise RuntimeError("Windows returned an invalid virtual desktop size.")
            nx = round((point.x - left) * 65535 / (width - 1))
            ny = round((point.y - top) * 65535 / (height - 1))
            if not (0 <= nx <= 65535 and 0 <= ny <= 65535):
                raise RuntimeError("Play click is outside the Windows virtual desktop.")
            self._send_mouse(MOUSE_MOVE | MOUSE_ABSOLUTE | MOUSE_VIRTUAL_DESKTOP,
                             dx=nx, dy=ny)
        self._move(point.x, point.y)
        self._send_mouse(MOUSE_MOVE)  # Notify games of the new cursor location.
        if self.stop.wait(PRECLICK_HOVER_SECONDS):
            return None

        for dx, dy in PRECLICK_WIGGLE_OFFSETS:
            if self.stop.is_set():
                return None
            self.check_focus()
            px = point.x + max(-x, min(dx, rect.right - 1 - x))
            py = point.y + max(-y, min(dy, rect.bottom - 1 - y))
            self._move(px, py)
            # Real Win32 movement, not only a visual SetCursorPos jump.
            self._send_mouse(MOUSE_MOVE)
            if self.stop.wait(PRECLICK_WIGGLE_SECONDS):
                return None

        self._move(point.x, point.y)
        self._send_mouse(MOUSE_MOVE)
        if self.stop.wait(PRECLICK_SETTLE_SECONDS):
            return None
        new_point, _ = self._validated_point(x, y, shape)
        if (new_point.x, new_point.y) != (point.x, point.y):
            raise RuntimeError("Roblox client shifted while preparing the click.")
        self._check_cursor(point.x, point.y)
        self.check_focus()
        return point

    def _direct_click(self, x, y, shape, method):
        point = self._prepare_click_target(x, y, shape)
        if point is None or self.stop.is_set():
            return False
        self._button_event(MOUSE_LEFT_DOWN, method)
        try:
            self.stop.wait(CLICK_HOLD_SECONDS)
        finally:
            self._button_event(MOUSE_LEFT_UP, method)
        return not self.stop.is_set()

    def _button_event(self, flag, method):
        if method == "event":
            # AutoHotkey Event-like Win32 mouse_event. Unlike SendInput this API
            # cannot report injection acceptance: menu-state validation is mandatory.
            self.user.mouse_event(flag, 0, 0, 0, 0)
        else:
            self._send_mouse(flag)

    def _click(self, x, y, shape, method):
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
            # SetCursorPos alone can move the visible pointer without
            # feeding Roblox's mouse-move input path. Inject real motion
            # events, then return to the exact intended pixel before clicking.
            self._send_mouse(MOUSE_MOVE, dx=1)
            self._send_mouse(MOUSE_MOVE, dx=-1)
            if self.stop.wait(JITTER_SECONDS):
                return False
        # Recenter after injected movement (Windows pointer acceleration may
        # round tiny relative moves). Keep the button-up at the same pixel.
        self._move(point.x, point.y)
        if self.stop.wait(POST_JITTER_SECONDS):
            return False
        final, _ = self._validated_point(x, y, shape)
        if (final.x, final.y) != (point.x, point.y):
            raise RuntimeError("Roblox moved before clicking. Restart navigation.")
        self._check_cursor(point.x, point.y)
        if self.stop.is_set():
            return False
        self._button_event(MOUSE_LEFT_DOWN, method)
        try:
            self.stop.wait(CLICK_HOLD_SECONDS)
        finally:
            # Always release even if F2 stops the macro during the click.
            self._button_event(MOUSE_LEFT_UP, method)
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

    def direct_click_absolute(self, x, y, shape):
        """Absolute SendInput move, hover and native wiggle, then click."""
        point = self._prepare_click_target(x, y, shape, absolute=True)
        if point is None or self.stop.is_set():
            return False
        self._button_event(MOUSE_LEFT_DOWN, "input")
        try:
            self.stop.wait(CLICK_HOLD_SECONDS)
        finally:
            self._button_event(MOUSE_LEFT_UP, "input")
        return not self.stop.is_set()

    def direct_click_message(self, x, y, shape):
        """Diagnostic WM_LBUTTONDOWN/UP delivered to Roblox's HWND.

        Some games ignore window messages and rely on raw device input; that is
        why this is a fallback, not a claim that messages bypass game controls.
        """
        point = self._prepare_click_target(x, y, shape)
        if point is None or self.stop.is_set():
            return False
        coordinate = ((int(y) & 0xffff) << 16) | (int(x) & 0xffff)
        if not self.user.PostMessageW(self.hwnd, WM_MOUSEMOVE, 0, coordinate):
            raise RuntimeError("Windows rejected the mouse-move window message.")
        if not self.user.PostMessageW(self.hwnd, WM_LBUTTONDOWN, 1, coordinate):
            raise RuntimeError("Windows rejected the left-button-down window message.")
        try:
            self.stop.wait(CLICK_HOLD_SECONDS)
        finally:
            if not self.user.PostMessageW(self.hwnd, WM_LBUTTONUP, 0, coordinate):
                raise RuntimeError("Windows rejected the left-button-up window message.")
        return not self.stop.is_set()
