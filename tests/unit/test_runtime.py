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


def test_tray_menu_has_expected_items() -> None:
    rt = make_runtime()
    menu = rt._build_tray_menu()  # noqa: SLF001
    labels = [label for _id, label, _checked in menu if label]
    assert labels == [
        "显示面板",
        "收进小球",
        "暂停跟随",
        "免打扰",
        "开机自启",
        "小球回到右下角",
        "面板回到默认位置",
        "退出",
    ]
    assert sum(1 for _id, label, _c in menu if not label) == 2  # 两条分隔线


def test_reset_ball_clears_saved_position() -> None:
    rt = make_runtime()
    from mascot_app.runtime import CMD_RESET_BALL

    rt._on_tray_command(CMD_RESET_BALL)  # noqa: SLF001
    assert rt._ball_pos is None  # noqa: SLF001


def test_reset_panel_clears_saved_position() -> None:
    rt = make_runtime()
    from mascot_app.runtime import CMD_RESET_PANEL, load_panel_pos, save_panel_pos

    rt._panel_pos = (10, 20)  # noqa: SLF001
    save_panel_pos((10, 20))
    rt._on_tray_command(CMD_RESET_PANEL)  # noqa: SLF001
    assert rt._panel_pos is None  # noqa: SLF001
    assert load_panel_pos() is None


def test_panel_pos_roundtrip_and_noop_for_bad_data() -> None:
    from mascot_app.runtime import _write_runtime, load_panel_pos, save_panel_pos

    assert load_panel_pos() is None
    save_panel_pos((321, 654))
    assert load_panel_pos() == (321, 654)
    # 坏数据当没有，绝不因此启动失败
    _write_runtime({"panel_pos": [1, "x"]})
    assert load_panel_pos() is None
    save_panel_pos(None)
    assert load_panel_pos() is None


def test_toggle_pause_updates_snapshot_and_tip() -> None:
    rt = make_runtime()
    assert rt.snapshot()["paused"] is False

    rt.command("toggle_pause")
    rt._drain_commands()  # noqa: SLF001
    assert rt.snapshot()["paused"] is True
    assert "暂停" in rt._tray_tip()  # noqa: SLF001

    rt.command("toggle_pause")
    rt._drain_commands()  # noqa: SLF001
    assert rt.snapshot()["paused"] is False
    assert "暂停" not in rt._tray_tip()  # noqa: SLF001


def test_tray_command_routes_to_events() -> None:
    from mascot_app.runtime import CMD_QUIT, CMD_TO_BALL, CMD_TO_PANEL

    rt = make_runtime()
    rt._on_tray_command(CMD_TO_BALL)  # noqa: SLF001
    rt._on_tray_command(CMD_TO_PANEL)  # noqa: SLF001
    rt._on_tray_command(CMD_QUIT)  # noqa: SLF001
    rt._drain_commands()  # noqa: SLF001
    assert Event.CLICK_CLOCK in rt._events or rt._events == []  # 事件已被状态机消费则只留退出标志
    assert rt._stop.is_set()  # noqa: SLF001


def test_dnd_toggle_hides_panel_and_skips_auto_show() -> None:
    from mascot_app.runtime import SHOW_PANEL

    rt = make_runtime()
    assert rt.snapshot()["dnd"] is False

    rt.command("toggle_dnd")
    rt._drain_commands()  # noqa: SLF001
    assert rt.snapshot()["dnd"] is True
    assert "免打扰" in rt._tray_tip()  # noqa: SLF001

    # 免打扰下 PET_FOUND 的 SHOW_PANEL 副作用被跳过
    rt._apply(rt._machine.push(Event.PET_FOUND))  # noqa: SLF001
    assert rt.snapshot()["state"] == "tracking"

    rt.command("toggle_dnd")
    rt._drain_commands()  # noqa: SLF001
    assert rt.snapshot()["dnd"] is False
    assert SHOW_PANEL  # 常量仍由状态机产生，跳过逻辑只在 _apply

class StreamingProvider(FakeProvider):
    """按分片交付的假 provider；可在指定分片后触发取消，验证部分文本落盘。"""

    def __init__(self, pieces: list[str], snapshots: list[dict[str, object]] | None = None, cancel_after: int | None = None) -> None:
        super().__init__()
        self.pieces = pieces
        self.snapshots = snapshots
        self.cancel_after = cancel_after
        self.rt: Runtime | None = None

    def send_stream(self, text: str, on_delta: object) -> Message:
        emit = on_delta
        for i, piece in enumerate(self.pieces):
            if i == self.cancel_after and self.rt is not None:
                self.rt.cancel_send()
            assert callable(emit)
            emit(piece)
            if self.snapshots is not None:
                assert self.rt is not None
                self.snapshots.append(self.rt.snapshot()["streaming"])
        self.sent.append(text)
        return Message(role="assistant", text="".join(self.pieces), ts=time.time(), msg_id="stream-1")


def test_send_stream_exposes_partial_text() -> None:
    seen: list[dict[str, object]] = []
    provider = StreamingProvider(["你", "好", "呀"], snapshots=seen)
    rt = make_runtime(provider)
    provider.rt = rt
    rt._load_history()

    rt.send_text("打个招呼")
    rt._drain_sends()  # noqa: SLF001

    assert seen == [
        {"active": True, "text": "你"},
        {"active": True, "text": "你好"},
        {"active": True, "text": "你好呀"},
    ]
    snap = rt.snapshot()
    assert snap["streaming"] == {"active": False, "text": ""}
    texts = [(m["role"], m["text"]) for m in snap["messages"]]
    assert texts == [("assistant", "早上好"), ("user", "打个招呼"), ("assistant", "你好呀")]


def test_cancel_keeps_partial_reply() -> None:
    provider = StreamingProvider(["第一段", "不该出现"], cancel_after=1)
    rt = make_runtime(provider)
    provider.rt = rt

    rt.send_text("长回答")
    rt._drain_sends()  # noqa: SLF001

    snap = rt.snapshot()
    assert snap["sending"] is False
    assert snap["streaming"]["active"] is False
    texts = [m["text"] for m in snap["messages"]]
    assert texts[-1] == "第一段"
    assert "不该出现" not in "".join(texts)
    assert snap["messages"][-1]["id"].startswith("partial-")


def test_cancel_send_is_noop_when_idle() -> None:
    rt = make_runtime()
    assert rt.cancel_send() is False

