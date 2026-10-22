"""Win32 绑定的最小集合（只包含本项目真正用到的 API）。

纪律：
- 所有函数在非 Windows 上抛 PlatformNotSupported，导入本身不炸（Linux 可跑单测）；
- 坐标一律物理像素（R-03）；矩形优先用 DWM 扩展边框，避免 Win10 阴影外扩。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

IS_WINDOWS = sys.platform == "win32"

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
GWL_EXSTYLE = -20
WM_CLOSE = 0x0010
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SWP_ASYNCWINDOWPOS = 0x4000
SW_SHOWNOACTIVATE = 4
SWP_NOACTIVATE = 0x0010
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
HWND_TOPMOST = -1
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0
PM_REMOVE = 0x0001
WM_DESTROY = 0x0002
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
DWMWA_EXTENDED_FRAME_BOUNDS = 9
ERROR_ALREADY_EXISTS = 183


class PlatformNotSupported(RuntimeError):
    """在非 Windows 上调用平台 API。"""


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wt.LONG), ("cy", wt.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise PlatformNotSupported("此 API 仅 Windows 可用")


if IS_WINDOWS:  # pragma: no branch - 平台分支
    _user32: Any = ctypes.windll.user32  # type: ignore[attr-defined]
    _gdi32: Any = ctypes.windll.gdi32  # type: ignore[attr-defined]
    _dwmapi: Any = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    _kernel32: Any = ctypes.windll.kernel32  # type: ignore[attr-defined]
else:
    _user32 = _gdi32 = _dwmapi = _kernel32 = None


def _declare_64bit_safe_prototypes() -> None:
    """显式声明 argtypes：64 位下不声明会导致句柄被截断成 32 位（经典崩溃）。"""
    u, g, k = _user32, _gdi32, _kernel32
    u.UpdateLayeredWindow.argtypes = [
        wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(SIZE),
        wt.HDC, ctypes.POINTER(wt.POINT), wt.DWORD, ctypes.POINTER(BLENDFUNCTION), wt.DWORD,
    ]
    u.UpdateLayeredWindow.restype = wt.BOOL
    u.SetWindowPos.argtypes = [
        wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT,
    ]
    u.CreateWindowExW.argtypes = [
        wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
    ]
    u.CreateWindowExW.restype = wt.HWND
    u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
    u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    u.EnumWindows.argtypes = [ctypes.c_void_p, wt.LPARAM]
    u.GetDC.argtypes = [wt.HWND]
    u.GetDC.restype = wt.HDC
    u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    u.DestroyWindow.argtypes = [wt.HWND]
    g.CreateCompatibleDC.argtypes = [wt.HDC]
    g.CreateCompatibleDC.restype = wt.HDC
    g.DeleteDC.argtypes = [wt.HDC]
    g.DeleteObject.argtypes = [wt.HANDLE]
    g.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
    g.SelectObject.restype = wt.HANDLE
    g.CreateDIBSection.argtypes = [
        wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD,
    ]
    g.CreateDIBSection.restype = wt.HANDLE
    u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    u.DefWindowProcW.restype = ctypes.c_ssize_t
    u.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
    u.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    u.DispatchMessageW.restype = ctypes.c_ssize_t
    u.RegisterClassW.argtypes = [ctypes.c_void_p]
    u.RegisterClassW.restype = wt.ATOM
    u.GetDesktopWindow.restype = wt.HWND
    k.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    k.GetModuleHandleW.restype = wt.HMODULE
    u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    u.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    u.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
    u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    u.GetWindowTextLengthW.argtypes = [wt.HWND]
    u.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    k.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
    k.CreateMutexW.restype = wt.HANDLE
    k.CloseHandle.argtypes = [wt.HANDLE]


if IS_WINDOWS:
    _declare_64bit_safe_prototypes()


def enable_dpi_awareness() -> str:
    """声明 DPI 感知，**只调用一次**（进程级）。返回实际生效的级别。"""
    _require_windows()
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        if _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per_monitor_v2"
    except (AttributeError, OSError):
        pass
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        if _shcore().SetProcessDpiAwareness(2) == 0:
            return "per_monitor"
    except (AttributeError, OSError):
        pass
    try:
        if _user32.SetProcessDPIAware():
            return "system"
    except (AttributeError, OSError):
        pass
    return "none"


def _shcore() -> Any:
    if not hasattr(_shcore, "_lib"):
        _shcore._lib = ctypes.windll.shcore  # type: ignore[attr-defined]
    return _shcore._lib  # type: ignore[attr-defined]


_WINFUNCTYPE: Any = getattr(ctypes, "WINFUNCTYPE", None)


def func_type() -> Any:
    """ctypes.WINFUNCTYPE 只在 Windows 存在，Linux 上由平台分支兜住。"""
    return _WINFUNCTYPE


def screen_metrics() -> tuple[int, int]:
    """主屏物理尺寸（SM_CXSCREEN 在 PerMonitorV2 下已是物理像素）。"""
    _require_windows()
    return int(_user32.GetSystemMetrics(0)), int(_user32.GetSystemMetrics(1))


def cursor_pos() -> tuple[int, int]:
    _require_windows()
    pt = wt.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def window_dpi(hwnd: int = 0) -> int:
    """窗口所在显示器 DPI（96 = 100%）。"""
    _require_windows()
    try:
        return int(_user32.GetDpiForWindow(hwnd or _user32.GetDesktopWindow()))
    except (AttributeError, OSError):
        dc = _user32.GetDC(0)
        dpi = int(_gdi32.GetDeviceCaps(dc, 88))  # LOGPIXELSX
        _user32.ReleaseDC(0, dc)
        return dpi


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """优先 DWM 扩展边框（不含 Win10 阴影），失败退回 GetWindowRect。"""
    _require_windows()
    r = RECT()
    try:
        if _dwmapi.DwmGetWindowAttribute(
            wt.HWND(hwnd), wt.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS), ctypes.byref(r), ctypes.sizeof(r)
        ) != 0:
            raise OSError("dwm failed")
    except (AttributeError, OSError):
        _user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r))
    return int(r.left), int(r.top), int(r.right - r.left), int(r.bottom - r.top)


def get_class_name(hwnd: int) -> str:
    _require_windows()
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(wt.HWND(hwnd), buf, 256)
    return buf.value


def get_pid(hwnd: int) -> int:
    _require_windows()
    pid = wt.DWORD()
    _user32.GetWindowThreadProcessId(wt.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def get_process_name(hwnd: int) -> str:
    """进程名；psutil 失败返回空串（不抛，保证枚举鲁棒）。"""
    if not IS_WINDOWS:
        raise PlatformNotSupported("仅 Windows")
    try:
        import psutil

        return str(psutil.Process(get_pid(hwnd)).name())
    except Exception:  # noqa: BLE001 - 枚举阶段任何进程都可能消失
        return ""


def is_visible(hwnd: int) -> bool:
    _require_windows()
    return bool(_user32.IsWindowVisible(wt.HWND(hwnd)))


def enum_windows() -> list[int]:
    """枚举所有顶层窗口（顺序即 Z 序）。"""
    _require_windows()
    out: list[int] = []
    EnumProc = func_type()(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd: int, _lparam: int) -> bool:
        out.append(int(hwnd))
        return True

    _user32.EnumWindows(EnumProc(_cb), 0)
    return out


def set_click_through(hwnd: int, enabled: bool) -> None:
    """WS_EX_TRANSPARENT：鼠标事件穿透到下层窗口。"""
    _require_windows()
    ex = _get_ex_style(hwnd)
    new = ex | WS_EX_TRANSPARENT if enabled else ex & ~WS_EX_TRANSPARENT
    if new != ex:
        _set_ex_style(hwnd, new)


def _get_ex_style(hwnd: int) -> int:
    try:
        return int(_user32.GetWindowLongPtrW(wt.HWND(hwnd), GWL_EXSTYLE))
    except (AttributeError, OSError):
        return int(_user32.GetWindowLongW(wt.HWND(hwnd), GWL_EXSTYLE))


def _set_ex_style(hwnd: int, style: int) -> None:
    try:
        _user32.SetWindowLongPtrW(wt.HWND(hwnd), GWL_EXSTYLE, ctypes.c_ssize_t(style))
    except (AttributeError, OSError):
        _user32.SetWindowLongW(wt.HWND(hwnd), GWL_EXSTYLE, style)


def move_window(hwnd: int, x: int, y: int) -> None:
    _require_windows()
    _user32.SetWindowPos(
        wt.HWND(hwnd), wt.HWND(HWND_TOPMOST), x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE
    )


def move_window_below(hwnd: int, x: int, y: int) -> None:
    """只改位置、不动 Z 序、不激活（跟随用；避免每帧抢焦点）。"""
    _require_windows()
    _user32.SetWindowPos(
        wt.HWND(hwnd),
        wt.HWND(0),
        x,
        y,
        0,
        0,
        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS,
    )


def show_window(hwnd: int, visible: bool) -> None:
    _require_windows()
    _user32.ShowWindow(wt.HWND(hwnd), SW_SHOWNOACTIVATE if visible else SW_HIDE)


def add_toolwindow(hwnd: int) -> None:
    """WS_EX_TOOLWINDOW：不出现在 Alt+Tab 与任务栏。"""
    _require_windows()
    _set_ex_style(hwnd, _get_ex_style(hwnd) | WS_EX_TOOLWINDOW)


def get_window_title(hwnd: int) -> str:
    _require_windows()
    n = int(_user32.GetWindowTextLengthW(wt.HWND(hwnd)))
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 2)
    _user32.GetWindowTextW(wt.HWND(hwnd), buf, n + 2)
    return buf.value


def find_window(title: str, *, exact: bool = True, timeout_s: float = 0.0) -> int:
    """按标题找顶层窗口（面板 HWND 的发现手段）。超时返回 0。"""
    _require_windows()
    import time

    deadline = time.monotonic() + timeout_s
    while True:
        for hwnd in enum_windows():
            text = get_window_title(hwnd)
            if (text == title) if exact else (title in text):
                return hwnd
        if time.monotonic() >= deadline:
            return 0
        time.sleep(0.05)


def post_close(hwnd: int) -> None:
    """投递 WM_CLOSE：让目标窗口走正常关闭流程。"""
    _require_windows()
    _user32.PostMessageW(wt.HWND(hwnd), WM_CLOSE, 0, 0)


def destroy_window(hwnd: int) -> None:
    _require_windows()
    _user32.DestroyWindow(wt.HWND(hwnd))


def create_mutex(name: str) -> tuple[int, bool]:
    """创建命名互斥体，返回 (句柄, 是否已存在)。"""
    _require_windows()
    handle = _kernel32.CreateMutexW(None, False, wt.LPCWSTR(name))
    already = _kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    return int(handle or 0), already


def close_handle(handle: int) -> None:
    _require_windows()
    if handle:
        _kernel32.CloseHandle(wt.HANDLE(handle))


def candidates(names: Iterable[str] | None = None) -> list[dict]:
    """可见窗口清单（调试/发现用）。"""
    _require_windows()
    out = []
    for hwnd in enum_windows():
        if not is_visible(hwnd):
            continue
        cls = get_class_name(hwnd)
        out.append(
            {
                "hwnd": hwnd,
                "class": cls,
                "process": get_process_name(hwnd),
                "rect": get_window_rect(hwnd),
            }
        )
    return out
