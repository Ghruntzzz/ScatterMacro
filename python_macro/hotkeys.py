"""Window-scoped global F1/F2 registration, without keyboard hooks."""
import ctypes
import re
from ctypes import wintypes


def parse_hotkey(value):
    parts = value.upper().split("+")
    if not parts or any(not p for p in parts):
        raise ValueError("Choose a valid keyboard shortcut.")
    modifiers = {"ALT":1, "CTRL":2, "SHIFT":4, "WIN":8}
    flags = 0x4000
    for part in parts[:-1]:
        if part not in modifiers or flags & modifiers[part]:
            raise ValueError("Use Ctrl, Shift, Alt or Win once per shortcut.")
        flags |= modifiers[part]
    key = parts[-1]
    named = {"ESC":0x1B, "ESCAPE":0x1B, "SPACE":0x20, "PAUSE":0x13,
             "HOME":0x24, "END":0x23, "INSERT":0x2D, "DELETE":0x2E,
             "PGUP":0x21, "PGDOWN":0x22, "UP":0x26, "DOWN":0x28,
             "LEFT":0x25, "RIGHT":0x27, "TAB":0x09, "RETURN":0x0D}
    if re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        code = 0x6F + int(key[1:])
    elif re.fullmatch(r"[A-Z0-9]", key) and flags != 0x4000:
        code = ord(key)
    elif key in named:
        code = named[key]
    else:
        raise ValueError("Use F1-F24, a named key, or a modified letter/number (such as Ctrl+F).")
    return flags, code


def validate_hotkeys(start, stop):
    if parse_hotkey(start) == parse_hotkey(stop):
        raise ValueError("Start and stop must use different shortcuts.")


class RuntimeHotkeys:
    START, STOP = 0x5301, 0x5302

    def __init__(self, hwnd, user=None, start_key="F1", stop_key="F2"):
        self.hwnd = hwnd
        self.user = user if user is not None else ctypes.windll.user32
        if user is None:
            self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.registered = []
        self.start_key, self.stop_key = start_key, stop_key

    def register(self):
        if self.registered:
            return
        validate_hotkeys(self.start_key, self.stop_key)
        for identifier, value in ((self.START, self.start_key), (self.STOP, self.stop_key)):
            modifiers, key = parse_hotkey(value)
            if not self.user.RegisterHotKey(self.hwnd, identifier, modifiers, key):
                self.close()
                raise RuntimeError(f"{value} is in use by another application. Choose another shortcut in Settings.")
            self.registered.append(identifier)

    def close(self):
        for identifier in self.registered:
            self.user.UnregisterHotKey(self.hwnd, identifier)
        self.registered.clear()
