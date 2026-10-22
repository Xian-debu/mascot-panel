"""本地聊天记录：解析 / 合并 / 去重 / 截断（纯逻辑，无需 Windows）。"""

from __future__ import annotations

import json

from mascot_core.contract import Message
from mascot_core.history import dump_history, filter_cleared, merge_history, parse_history


def _m(role: str, text: str, ts: float = 0.0, mid: str = "") -> Message:
    return Message(role=role, text=text, ts=ts, msg_id=mid)


def test_parse_valid_records() -> None:
    raw = json.dumps(
        {
            "version": 1,
            "messages": [
                {"role": "user", "text": "你好", "ts": 1.5, "id": "local-0"},
                {"role": "assistant", "text": "在的", "ts": 2.5, "id": "reply-1"},
            ],
        }
    )
    out = parse_history(raw)
    assert [(m.role, m.text, m.msg_id) for m in out] == [
        ("user", "你好", "local-0"),
        ("assistant", "在的", "reply-1"),
    ]


def test_parse_accepts_bare_list_and_missing_fields() -> None:
    raw = json.dumps([{"role": "user", "text": "hi"}, {"role": "assistant", "text": "ok", "ts": "bad"}])
    out = parse_history(raw)
    assert len(out) == 2
    assert out[0].ts == 0.0
    assert out[1].ts == 0.0
    assert out[0].msg_id == ""


def test_parse_broken_input_never_raises() -> None:
    assert parse_history("not json") == []
    assert parse_history("") == []
    assert parse_history('{"messages": 42}') == []
    assert parse_history('{"messages": [{"role": "system", "text": "x"}]}') == []
    assert parse_history('{"messages": [{"role": "user", "text": ""}]}') == []
    assert parse_history('{"messages": [{"role": "user", "text": 7}]}') == []


def test_parse_truncates_overlong_text() -> None:
    raw = json.dumps({"messages": [{"role": "user", "text": "x" * 9000}]})
    out = parse_history(raw)
    assert len(out) == 1 and len(out[0].text) == 4000


def test_dump_parse_roundtrip() -> None:
    msgs = [_m("user", "早", 1.0, "local-0"), _m("assistant", "早呀", 2.0, "reply-7")]
    assert parse_history(dump_history(msgs)) == msgs


def test_merge_dedupes_by_id() -> None:
    a = [_m("user", "早", 1.0, "local-0"), _m("assistant", "早呀", 2.0, "reply-1")]
    b = [_m("assistant", "早呀", 2.0, "reply-1"), _m("user", "今天干嘛", 3.0, "local-2")]
    out = merge_history(a, b, limit=50)
    assert [m.text for m in out] == ["早", "早呀", "今天干嘛"]


def test_merge_dedupes_by_content_when_no_id() -> None:
    a = [_m("assistant", "离线模式", 0.0, "offline-0")]
    b = [_m("assistant", "离线模式", 0.0, "")]
    out = merge_history(b, a, limit=50)
    assert len(out) == 1


def test_merge_sorts_by_ts_and_keeps_tail() -> None:
    a = [_m("user", "晚", 9.0, "x9"), _m("user", "早", 1.0, "x1")]
    b = [_m("user", "中", 5.0, "x5")]
    out = merge_history(a, b, limit=2)
    assert [m.text for m in out] == ["中", "晚"]


def test_merge_of_nothing_is_empty() -> None:
    assert merge_history([], [], limit=10) == []


def test_filter_cleared_drops_matching_ids() -> None:
    msgs = [_m("user", "旧问题", 1.0, "legacy-1"), _m("assistant", "旧回答", 2.0, "legacy-2")]
    out = filter_cleared(msgs, {"legacy-1", "legacy-2"})
    assert out == []


def test_filter_cleared_keeps_uncleared() -> None:
    msgs = [_m("user", "旧", 1.0, "legacy-1"), _m("user", "新", 3.0, "legacy-3")]
    out = filter_cleared(msgs, {"legacy-1"})
    assert [m.text for m in out] == ["新"]


def test_filter_cleared_without_set_is_copy() -> None:
    msgs = [_m("user", "a", 1.0, "local-1")]
    out = filter_cleared(msgs, set())
    assert out == msgs and out is not msgs


def test_filter_cleared_keeps_messages_without_id() -> None:
    msgs = [_m("assistant", "无 id", 1.0, "")]
    assert filter_cleared(msgs, {"legacy-1"}) == msgs
