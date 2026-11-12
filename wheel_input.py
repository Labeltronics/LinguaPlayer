"""Windows low-level wheel hook scoped strictly to this foreground video rectangle."""
import ctypes
from ctypes import wintypes
class NativeWheelHook:
    def __init__(self,owner):
        self.owner=owner;self.user=ctypes.WinDLL('user32',use_last_error=True);self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        class Data(ctypes.Structure):_fields_=[('pt',wintypes.POINT),('mouseData',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
        self.callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        self.user.SetWindowsHookExW.restype=wintypes.HANDLE;self.user.SetWindowsHookExW.argtypes=[ctypes.c_int,self.callback_type,wintypes.HINSTANCE,wintypes.DWORD]
        self.user.CallNextHookEx.restype=ctypes.c_ssize_t;self.user.CallNextHookEx.argtypes=[wintypes.HANDLE,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM]
        self.user.GetForegroundWindow.restype=wintypes.HWND;self.user.GetAncestor.restype=wintypes.HWND;self.user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
        self.user.UnhookWindowsHookEx.argtypes=[wintypes.HANDLE];self.kernel.GetModuleHandleW.restype=wintypes.HMODULE
        @self.callback_type
        def callback(code,message,param):
            try:
                if code>=0 and message==0x020A and not owner.closing and (owner.path or getattr(owner,'stream_url','')):
                    host=owner.pip or owner
                    if self.user.GetAncestor(self.user.GetForegroundWindow(),2)==int(host.winId()) and host.isVisible() and not host.isMinimized() and not (self.user.GetAsyncKeyState(0x11)&0x8000):
                        data=ctypes.cast(param,ctypes.POINTER(Data)).contents
                        # Win32 hook coordinates are physical; Qt global positions may be DPI scaled.
                        rect=wintypes.RECT();self.user.GetWindowRect(wintypes.HWND(int(owner.video.winId())),ctypes.byref(rect))
                        if rect.left<=data.pt.x<rect.right and rect.top<=data.pt.y<rect.bottom:
                            delta=ctypes.c_short((data.mouseData>>16)&0xffff).value;owner.handle_video_wheel(delta);return 1
            except Exception:pass
            return self.user.CallNextHookEx(None,code,message,param)
        self.callback=callback;self.handle=self.user.SetWindowsHookExW(14,self.callback,self.kernel.GetModuleHandleW(None),0)
        if not self.handle:raise OSError('Mouse hook tidak tersedia')
    def close(self):
        if self.handle:self.user.UnhookWindowsHookEx(self.handle);self.handle=None
