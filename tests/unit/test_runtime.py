"""Runtime 的纯逻辑部分（不碰窗口）：快照结构、面板 HTML 打包、投递事件。"""

from __future__ import annotations

from mascot_app.providers.null import NullProvider
from mascot_app.runtime import Runtime, load_panel_html
from mascot_core.config import Settings
from mascot_core.state import State


def make_runtime() -> Runtime:
    return Runtime(Settings(), NullProvider())


def test_snapshot_shape() -> None:
    snap = make_runtime().snapshot()
    assert snap["state"] == State.IDLE.value
    assert snap["provider"] == "null"
    assert snap["pet"] is None
    assert snap["degraded"] is False
    assert set(snap) >= {"state", "reason", "degraded", "provider", "pet", "uptime_s"}


def test_to_ball_queues_event() -> None:
    rt = make_runtime()
    rt.to_ball()
    assert len(rt._events) == 1  # noqa: SLF001 - 测试独占，检查投递而不是窗口


def test_panel_html_is_packaged() -> None:
    html = load_panel_html()
    assert "天选姬" in html
    assert "pywebview.api" in html
    assert "mascot-panel" in html
