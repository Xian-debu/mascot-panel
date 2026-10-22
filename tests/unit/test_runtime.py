"""Runtime 的纯逻辑部分（不碰窗口）：快照结构、面板合成、聊天队列。"""

from __future__ import annotations

import time

from mascot_app.providers.null import NullProvider
from mascot_app.runtime import Runtime, load_panel_html
from mascot_core.config import Settings
from mascot_core.contract import HealthState, Message, ProviderHealth
from mascot_core.state import Event, State


class FakeProvider:
    name = "fake"

    def __init__(self, reply: str = "好的", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.sent: list[str] = []
        self._history = [Message(role="assistant", text="早上好", ts=time.time(), msg_id="a0")]

    def health(self) -> ProviderHealth:
        return ProviderHealth(state=HealthState.UP)

    def history(self, limit: int = 50) -> list[Message]:
        return self._history[-limit:]

    def send(self, text: str) -> Message:
        if self.fail:
            raise ConnectionError("backend is gone")
        self.sent.append(text)
        return Message(role="assistant", text=self.reply, ts=time.time(), msg_id=f"a{len(self.sent)}")

    def stop(self) -> None:
        return None


def make_runtime(provider: object | None = None) -> Runtime:
    return Runtime(Settings(), provider or NullProvider())  # type: ignore[arg-type]


def test_snapshot_shape() -> None:
    snap = make_runtime().snapshot()
    assert snap["state"] == State.IDLE.value
    assert snap["provider"] == "null"
    assert snap["pet"] is None
    assert snap["degraded"] is False
    assert snap["sending"] is False
    assert snap["messages"] == []
    assert set(snap) >= {"state", "reason", "degraded", "provider", "pet", "uptime_s", "provider_detail"}


def test_to_ball_queues_event() -> None:
    rt = make_runtime()
    rt.to_ball()
    assert len(rt._events) == 1  # noqa: SLF001 - 测试独占，检查投递而不是窗口


def test_panel_html_is_composed() -> None:
    html = load_panel_html()
    assert "天选姬" in html
    assert "pywebview.api" in html
    assert "mascot-panel" in html
    assert "M.initComposer" in html


def test_send_pipeline_appends_user_and_reply() -> None:
    provider = FakeProvider(reply="收到")
    rt = make_runtime(provider)
    rt._load_history()  # noqa: SLF001
    assert [m["text"] for m in rt.snapshot()["messages"]] == ["早上好"]

    assert rt.send_text("在吗")["ok"] is True
    assert rt.send_text("   ")["ok"] is False
    rt._drain_sends()  # noqa: SLF001

    texts = [(m["role"], m["text"]) for m in rt.snapshot()["messages"]]
    assert texts == [("assistant", "早上好"), ("user", "在吗"), ("assistant", "收到")]
    assert provider.sent == ["在吗"]
    assert rt.snapshot()["sending"] is False


def test_send_failure_degrades_without_crashing() -> None:
    rt = make_runtime(FakeProvider(fail=True))
    rt.send_text("会失败")
    rt._drain_sends()  # noqa: SLF001
    snap = rt.snapshot()
    assert "backend is gone" in snap["error"]
    assert snap["sending"] is False
    assert Event.PROVIDER_DOWN in rt._events  # noqa: SLF001 - 交给状态机处理降级


def test_history_failure_is_soft() -> None:
    class Broken(FakeProvider):
        def history(self, limit: int = 50) -> list[Message]:
            raise OSError("no history")

    rt = make_runtime(Broken())
    rt._load_history()  # noqa: SLF001
    snap = rt.snapshot()
    assert snap["messages"] == []
    assert "no history" in snap["provider_detail"]
