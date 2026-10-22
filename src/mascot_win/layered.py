"""自绘分层窗口：PIL 图像 -> UpdateLayeredWindow，带真实 alpha 与点击穿透。

为什么不用 pywebview 做球：球是每帧变化的纯色块，走 HTML 反而贵；
面板需要富文本才用 WebView2（R-01）。两者共存在同一个进程里（见 M1 spike）。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import uuid

from PIL import Image, ImageChops

from mascot_win import win32

WNDPROC = win32.func_type()(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class LayeredWindow:
    """一个 32bpp 自绘窗口；render() 是幂等的，move() 只改位置。"""

    def __init__(self, width: int, height: int, *, click_through: bool = True) -> None:
        win32._require_windows()
        self.width = int(width)
        self.height = int(height)
        self._click_through = click_through
        self._class_name = f"mascot_layered_{uuid.uuid4().hex[:8]}"
        self._proc = WNDPROC(self._on_message)

        hinst = win32._kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._proc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = self._class_name
        if not win32._user32.RegisterClassW(ctypes.byref(wc)):
            raise OSError("RegisterClassW failed")

        ex = (
            win32.WS_EX_LAYERED
            | win32.WS_EX_TOOLWINDOW
            | win32.WS_EX_TOPMOST
            | win32.WS_EX_NOACTIVATE
            | (win32.WS_EX_TRANSPARENT if click_through else 0)
        )
        hwnd = win32._user32.CreateWindowExW(
            ex, self._class_name, "mascot", win32.WS_POPUP, 0, 0, self.width, self.height,
            None, None, hinst, None,
        )
        if not hwnd:
            raise OSError("CreateWindowExW failed")
        self.hwnd = int(hwnd)
        win32._user32.ShowWindow(wt.HWND(self.hwnd), win32.SW_SHOWNOACTIVATE)
        self._saved: Image.Image | None = None

    def _on_message(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == win32.WM_DESTROY:
            win32._user32.PostQuitMessage(0)
            return 0
        if msg == win32.WM_NCHITTEST and self._click_through:
            return win32.HTTRANSPARENT
        return int(
            win32._user32.DefWindowProcW(
                wt.HWND(hwnd), wt.UINT(msg), wt.WPARAM(wparam), wt.LPARAM(lparam)
            )
        )

    def render(self, image: Image.Image) -> None:
        """image 必须是 RGBA；内部做预乘（UpdateLayeredWindow 要求预乘 alpha）。"""
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)
        self._saved = image
        r, g, b, a = image.split()
        prem = Image.merge(
            "RGBA",
            (ImageChops.multiply(r, a), ImageChops.multiply(g, a), ImageChops.multiply(b, a), a),
        )
        raw = prem.tobytes("raw", "BGRA")

        bmi = win32.BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(bmi)
        bmi.biWidth = self.width
        bmi.biHeight = -self.height  # 负数 = top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = win32.BI_RGB

        screen_dc = win32._user32.GetDC(0)
        mem_dc = win32._gdi32.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        hbmp = win32._gdi32.CreateDIBSection(
            screen_dc, ctypes.byref(bmi), win32.DIB_RGB_COLORS, ctypes.byref(bits), None, 0
        )
        try:
            ctypes.memmove(bits, raw, len(raw))
            old = win32._gdi32.SelectObject(mem_dc, hbmp)
            dst = wt.POINT(0, 0)
            src = wt.POINT(0, 0)
            size = win32.SIZE(self.width, self.height)
            blend = win32.BLENDFUNCTION(win32.AC_SRC_OVER, 0, 255, win32.AC_SRC_ALPHA)
            win32._user32.UpdateLayeredWindow(
                wt.HWND(self.hwnd), screen_dc, ctypes.byref(dst), ctypes.byref(size),
                mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), win32.ULW_ALPHA,
            )
            win32._gdi32.SelectObject(mem_dc, old)
        finally:
            win32._gdi32.DeleteObject(hbmp)
            win32._gdi32.DeleteDC(mem_dc)
            win32._user32.ReleaseDC(0, screen_dc)

    def move(self, x: int, y: int) -> None:
        win32.move_window(self.hwnd, int(x), int(y))

    def set_click_through(self, enabled: bool) -> None:
        self._click_through = enabled
        win32.set_click_through(self.hwnd, enabled)

    def pump(self) -> int:
        """处理本线程窗口消息，返回处理条数。"""
        msg = wt.MSG()
        n = 0
        while win32._user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, win32.PM_REMOVE):
            win32._user32.TranslateMessage(ctypes.byref(msg))
            win32._user32.DispatchMessageW(ctypes.byref(msg))
            n += 1
        return n

    def destroy(self) -> None:
        if self.hwnd:
            win32.destroy_window(self.hwnd)
            self.hwnd = 0
