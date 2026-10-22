"""跟随目标发现：按窗口类名 + 进程名找桌宠窗口，拿物理像素矩形。

设计要点（旧实现教训）：
- 目标可能重开（句柄失效），每帧都要校验 IsWindow；
- 连续 N 帧找不到才算"丢失"，避免宠物播放动画时短暂隐藏导致面板闪烁；
- 只读，绝不 SetForegroundWindow / 注入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mascot_win import win32

if TYPE_CHECKING:
    from collections.abc import Sequence

from mascot_core.geometry import Rect


@dataclass(frozen=True, slots=True)
class TrackedWindow:
    hwnd: int
    class_name: str
    process: str
    rect: Rect


class PetTracker:
    def __init__(
        self,
        class_names: Sequence[str] = (),
        process_names: Sequence[str] = (),
        lost_frames: int = 3,
    ) -> None:
        self.class_names = tuple(c.lower() for c in class_names if c)
        self.process_names = tuple(p.lower() for p in process_names if p)
        self.lost_frames = max(1, int(lost_frames))
        self._missing = 0
        self._hwnd = 0

    def _matches(self, hwnd: int) -> bool:
        cls = win32.get_class_name(hwnd).lower()
        if self.class_names and any(c in cls for c in self.class_names):
            return True
        proc = win32.get_process_name(hwnd).lower()
        return bool(self.process_names) and proc in self.process_names

    def poll(self) -> TrackedWindow | None:
        if self._hwnd and win32.is_visible(self._hwnd) and self._matches(self._hwnd):
            x, y, w, h = win32.get_window_rect(self._hwnd)
            if w > 0 and h > 0:
                self._missing = 0
                return TrackedWindow(self._hwnd, win32.get_class_name(self._hwnd), "", Rect(x, y, w, h))
            self._hwnd = 0

        for hwnd in win32.enum_windows():
            if not win32.is_visible(hwnd) or hwnd == 0:
                continue
            if win32.get_class_name(hwnd) in ("Progman", "WorkerW", "Shell_TrayWnd"):
                continue
            if self._matches(hwnd):
                x, y, w, h = win32.get_window_rect(hwnd)
                if w > 0 and h > 0:
                    self._hwnd = hwnd
                    self._missing = 0
                    return TrackedWindow(hwnd, win32.get_class_name(hwnd), win32.get_process_name(hwnd), Rect(x, y, w, h))

        self._missing += 1
        if self._missing >= self.lost_frames:
            self._hwnd = 0
        return None
