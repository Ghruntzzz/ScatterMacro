"""Read-only Roblox client capture. Never attaches to process memory."""
import ctypes
from ctypes import wintypes

import mss
import numpy as np


def roblox_windows():
    user = ctypes.windll.user32
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        title = ctypes.create_unicode_buffer(512)
        user.GetWindowTextW(hwnd, title, len(title))
        if user.IsWindowVisible(hwnd) and title.value == "Roblox":
            found.append((int(hwnd), title.value))
        return True

    user.EnumWindows(callback_type(visit), 0)
    return found


def capture_client(hwnd):
    user = ctypes.windll.user32
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user.IsIconic.argtypes = [wintypes.HWND]
    rect, origin = wintypes.RECT(), wintypes.POINT()
    if user.IsIconic(hwnd) or not user.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Restore the Roblox window before capturing.")
    if not user.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise RuntimeError("Roblox window is no longer available.")
    width, height = rect.right, rect.bottom
    if width <= 0 or height <= 0:
        raise RuntimeError("Roblox has no visible client area.")
    with mss.mss() as screen:
        frame = screen.grab(dict(left=origin.x, top=origin.y, width=width, height=height))
        return np.asarray(frame).copy()
