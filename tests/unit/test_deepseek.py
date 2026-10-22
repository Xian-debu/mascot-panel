from __future__ import annotations

import urllib.request

from mascot_app.providers.deepseek import DeepSeekProvider
from mascot_core.contract import HealthState, Message


class _Resp:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._lines)

    def read(self, n: int = -1) -> bytes:
        return b"{}"


def test_health_without_key_is_down(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    health = DeepSeekProvider().health()
    assert health.state is HealthState.DOWN
    assert health.reason_code == "NO_API_KEY"


def test_history_is_empty_local_truth() -> None:
    assert DeepSeekProvider().history() == []


def test_set_context_drops_empty_and_keeps_roles() -> None:
    p = DeepSeekProvider()
    p.set_context(
        [
            Message(role="user", text="你好"),
            Message(role="assistant", text=""),
            Message(role="assistant", text="在"),
        ]
    )
    assert list(p._convo) == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "在"},
    ]


def test_send_stream_parses_sse_and_remembers_turns(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_AUTH_TOKEN", "test-key")
    lines = [
        b'data: {"choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}\n',
        b'data: {"choices":[{"delta":{"content":"\xe5\xa5\xbd"}}]}\n',
        b"data: [DONE]\n",
    ]
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _Resp(lines))
    p = DeepSeekProvider()
    deltas: list[str] = []
    msg = p.send_stream("hi", deltas.append)
    assert msg.role == "assistant"
    assert msg.text == "你好"
    assert deltas == ["你", "好"]
    assert list(p._convo)[-2:] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "你好"},
    ]


def test_anthropic_base_url_is_normalized() -> None:
    p = DeepSeekProvider(base_url="https://api.deepseek.com/anthropic/")
    assert p.base_url == "https://api.deepseek.com"
