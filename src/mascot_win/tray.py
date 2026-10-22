"""托盘图标 + 右键菜单（Shell_NotifyIcon）。

为什么放 win 层：这是纯 Win32 集成，和渲染/状态机无关；菜单内容由 app 层给。
窗口是隐藏的顶层 popup（不能用 message-only 窗口：TrackPopupMenu 需要前景窗口才能正常收起）。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import uuid
from collections.abc import Callable, Sequence

from mascot_win import win32
from mascot_win.layered import WNDCLASSW, WNDPROC


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wt.DWORD),
        ("Data2", wt.WORD),
        ("Data3", wt.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HANDLE),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutVersion", wt.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wt.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wt.HANDLE),
    ]


MenuItem = tuple[int, str, bool]  # id, 文案（空串=分隔线）, 是否勾选


class TrayIcon:
    """一个托盘图标；菜单每次右键现构建，勾选状态实时反映。"""

    def __init__(
        self,
        *,
        tip: str,
        build_menu: Callable[[], Sequence[MenuItem]],
        on_command: Callable[[int], None],
        on_double_click: Callable[[], None] | None = None,
    ) -> None:
        win32._require_windows()
        self._tip = tip[:120]
        self._build_menu = build_menu
        self._on_command = on_command
        self._on_double_click = on_double_click
        self._uid = 1
        self._cb_msg = win32.WM_APP + 1
        self._class_name = f"mascot_tray_{uuid.uuid4().hex[:8]}"
        self._proc = WNDPROC(self._on_message)

        hinst = win32._kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._class_name
        if not win32._user32.RegisterClassW(ctypes.byref(wc)):
            raise OSError("RegisterClassW failed (tray)")

        hwnd = win32._user32.CreateWindowExW(
            0, self._class_name, "mascot-tray", win32.WS_POPUP, 0, 0, 0, 0, None, None, hinst, None,
        )
        if not hwnd:
            raise OSError("CreateWindowExW failed (tray)")
        self.hwnd = int(hwnd)
        self._icon = self._load_icon()
        self._add()

    # ---- 图标 ----
    def _load_icon(self) -> int:
        try:
            icon = win32._shell32.ExtractIconW(None, sys.executable, 0)
            if icon:
                return int(icon)
        except OSError:
            pass
        return int(win32._user32.LoadIconW(None, ctypes.c_void_p(win32.IDI_APPLICATION)))

    def _data(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = wt.HWND(self.hwnd)
        nid.uID = self._uid
        nid.uFlags = win32.NIF_MESSAGE | win32.NIF_ICON | win32.NIF_TIP
        nid.uCallbackMessage = self._cb_msg
        nid.hIcon = wt.HANDLE(self._icon)
        nid.szTip = self._tip
        return nid

    def _add(self) -> None:
        if not win32._shell32.Shell_NotifyIconW(win32.NIM_ADD, ctypes.byref(self._data())):
            raise OSError("Shell_NotifyIconW(NIM_ADD) failed")

    def update_tip(self, tip: str) -> None:
        self._tip = tip[:120]
        win32._shell32.Shell_NotifyIconW(win32.NIM_MODIFY, ctypes.byref(self._data()))

    # ---- 菜单 ----
    def _show_menu(self) -> None:
        menu = win32._user32.CreatePopupMenu()
        if not menu:
            return
        try:
            for item_id, label, checked in self._build_menu():
                if not label:
                    win32._user32.AppendMenuW(menu, win32.MF_SEPARATOR, 0, None)
                    continue
                flags = win32.MF_STRING | (win32.MF_CHECKED if checked else 0)
                win32._user32.AppendMenuW(menu, flags, item_id, label)
            x, y = win32.cursor_pos()
            win32._user32.SetForegroundWindow(wt.HWND(self.hwnd))
            cmd = win32._user32.TrackPopupMenu(
                menu, win32.TPM_RIGHTBUTTON | win32.TPM_RETURNCMD, x, y, 0, wt.HWND(self.hwnd), None,
            )
            win32._user32.PostMessageW(wt.HWND(self.hwnd), win32.WM_APP + 2, 0, 0)
            if cmd:
                self._on_command(int(cmd))
        finally:
            win32._user32.DestroyMenu(menu)

    def _on_message(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == self._cb_msg:
            event = int(lparam) & 0xFFFF
            if event == win32.WM_RBUTTONUP:
                self._show_menu()
                return 0
            if event == win32.WM_LBUTTONDBLCLK:
                if self._on_double_click is not None:
                    self._on_double_click()
                return 0
            return 0
        return int(
            win32._user32.DefWindowProcW(
                wt.HWND(hwnd), wt.UINT(msg), wt.WPARAM(wparam), wt.LPARAM(lparam)
            )
        )

    def destroy(self) -> None:
        win32._shell32.Shell_NotifyIconW(win32.NIM_DELETE, ctypes.byref(self._data()))
        win32._user32.DestroyWindow(wt.HWND(self.hwnd))
        self.hwnd = 0
