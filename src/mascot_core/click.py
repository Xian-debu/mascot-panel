"""待机球点击判定（纯逻辑，无 Win32 依赖）。

待机球上单击要开面板、双击要回右下角，两者都以“按下又抬起且没拖动”为触发点，
只能靠时间窗区分：第一次点击先挂起，窗口内再来一次算双击，超时算单击。

不用 Win32 的 WM_LBUTTONDBLCLK 是有意的：它要求窗口类带 CS_DBLCLKS，而且系统仍会
先送一次普通单击消息，“第一次单击已经打开面板”的副作用无法撤回。
"""

from __future__ import annotations

CLICK_WINDOW_MS = 350.0
SINGLE = "single"
DOUBLE = "double"


class ClickGate:
    """把一串点击折叠成 single / double。

    调用方每收到一次“点击”（抬起且未拖动）就调一次 click()，每轮循环调 tick()。
    超时未 tick 的挂起点击会被后续 click() 丢弃（正常循环 10fps，不会发生）。
    """

    def __init__(self, window_ms: float = CLICK_WINDOW_MS) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms 必须大于 0")
        self.window_ms = float(window_ms)
        self._first_ms: float | None = None

    @property
    def pending(self) -> bool:
        return self._first_ms is not None

    def click(self, now_ms: float) -> str | None:
        """记一次点击：窗口内的第二次返回 "double"，第一次返回 None（等超时）。"""
        first = self._first_ms
        if first is not None and now_ms - first <= self.window_ms:
            self._first_ms = None
            return DOUBLE
        self._first_ms = now_ms
        return None

    def tick(self, now_ms: float) -> str | None:
        """挂起的点击是否已经超时：是则返回 "single" 并清空，否则 None。"""
        first = self._first_ms
        if first is None:
            return None
        if now_ms - first > self.window_ms:
            self._first_ms = None
            return SINGLE
        return None

    def reset(self) -> None:
        """放弃挂起的点击（拖动开始、切窗口等场景）。"""
        self._first_ms = None
