"""Foreground-filtered recording; F3 polling and raw relative mouse input."""
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QObject,QTimer,Signal
from python_macro.pathing import PathRecording


class Device(ctypes.Structure):
    _fields_=[('page',wintypes.USHORT),('usage',wintypes.USHORT),
              ('flags',wintypes.DWORD),('target',wintypes.HWND)]


class Header(ctypes.Structure):
    _fields_=[('type',wintypes.DWORD),('size',wintypes.DWORD),
              ('device',wintypes.HANDLE),('wparam',wintypes.WPARAM)]


class Mouse(ctypes.Structure):
    _fields_=[('flags',wintypes.USHORT),('buttons',wintypes.ULONG),
              ('raw',wintypes.ULONG),('dx',wintypes.LONG),('dy',wintypes.LONG),('extra',wintypes.ULONG)]


class PathRecorder(QObject):
    finished=Signal(str)
    failed=Signal(str)

    def __init__(self,client,mode,window):
        super().__init__(window)
        self.client=client
        self.target=int(window.winId())
        self.mode=mode
        self.recording=None
        self.active=False
        self.registered=False
        self.timer=QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.sample)

    def start(self):
        user=self.client.user
        if self.mode!='Keyboard':
            user.RegisterRawInputDevices.argtypes=[ctypes.POINTER(Device),wintypes.UINT,wintypes.UINT]
            user.RegisterRawInputDevices.restype=wintypes.BOOL
            user.GetRawInputData.argtypes=[wintypes.HANDLE,wintypes.UINT,ctypes.c_void_p,
                                          ctypes.POINTER(wintypes.UINT),wintypes.UINT]
            user.GetRawInputData.restype=wintypes.UINT
            device=Device(1,2,0x100,self.target)
            if not user.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(Device)):
                raise RuntimeError('Windows could not start mouse recording.')
            self.registered=True
        try:
            if not self.client.focus_roblox():
                raise RuntimeError('Could not focus Roblox.')
            self.recording=PathRecording(self.mode)
            self.active=True
            self.sample()
            self.timer.start()
        except Exception:
            self.cleanup()
            raise

    def sample(self,dx=0,dy=0):
        if not self.active:
            return
        user=self.client.user
        if user.GetAsyncKeyState(0x72)&0x8000:  # F3, irrespective of foreground.
            self.finish()
            return
        focused=user.GetForegroundWindow()==self.client.hwnd
        keys=[key for key in 'WASD' if focused and user.GetAsyncKeyState(ord(key))&0x8000]
        look=focused and bool(user.GetAsyncKeyState(2)&0x8000)
        if not self.recording.sample(focused,keys,look,dx,dy):
            self.finish()

    def raw_mouse(self,lparam):
        if not self.active or self.mode=='Keyboard':
            return
        size=wintypes.UINT()
        user=self.client.user
        if user.GetRawInputData(lparam,0x10000003,None,ctypes.byref(size),ctypes.sizeof(Header))==0xffffffff:
            return
        if not ctypes.sizeof(Header)+ctypes.sizeof(Mouse)<=size.value<=4096:
            return
        buffer=ctypes.create_string_buffer(size.value)
        if user.GetRawInputData(lparam,0x10000003,buffer,ctypes.byref(size),ctypes.sizeof(Header))==0xffffffff:
            return
        header=Header.from_buffer(buffer)
        if header.type==0:
            mouse=Mouse.from_buffer(buffer,ctypes.sizeof(Header))
            if not mouse.flags&1:  # Absolute tablet packets aren't relative movement.
                self.sample(mouse.dx,mouse.dy)

    def cleanup(self):
        self.active=False
        self.timer.stop()
        if self.registered:
            device=Device(1,2,1,None)
            self.client.user.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(Device))
            self.registered=False

    def finish(self):
        if not self.active:
            return
        self.cleanup()
        try:
            self.finished.emit(self.recording.finish())
        except ValueError as error:
            self.failed.emit(str(error))
