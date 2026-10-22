"""Legacy provider 契约测试：用一个模拟旧后端的 HTTP 服务验证翻译层。

不启动真的 deepseek-chat-rebuild（它要 API Key），只验证协议翻译：
news 标题前缀 → role、SSE 分片拼接、[SESSION:] 记住会话、健康态映射。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mascot_app.providers.legacy import LegacyProvider
from mascot_core.contract import HealthState


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:  # 静音
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server 约定
        if self.path.startswith("/api/pet/status"):
            self._json({"status": "ok", "engine": "ready", "sessions": 1, "total_messages": 4})
            return
        if self.path.startswith("/api/pet/news"):
            self._json(
                {
                    "code": 202000,
                    "data": [
                        {"id": 1, "title": "主人: 在吗", "description": "在吗"},
                        {"id": 2, "title": "天选姬: 在的", "description": "在的~"},
                    ],
                }
            )
            return
        self._json({"detail": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        if not self.path.startswith("/api/pet/ask"):
            self._json({"detail": "not found"}, 404)
            return
        reply = f"收到：{body.get('message', '')}"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()
        for piece in ("收到：", body.get("message", "")):
            self.wfile.write(f"data: {piece}\n\n".encode())
        self.wfile.write(b"data: [SESSION:sess-42]\n\n")
        self.wfile.flush()
        assert reply


@pytest.fixture()
def legacy_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_health_maps_ok(legacy_url: str) -> None:
    provider = LegacyProvider(legacy_url)
    health = provider.health()
    assert health.state is HealthState.UP
    assert health.latency_ms is not None


def test_history_translates_news_titles_to_roles(legacy_url: str) -> None:
    provider = LegacyProvider(legacy_url)
    messages = provider.history()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert [m.text for m in messages] == ["在吗", "在的~"]


def test_send_joins_sse_chunks_and_remembers_session(legacy_url: str) -> None:
    provider = LegacyProvider(legacy_url)
    reply = provider.send("你好")
    assert reply.role == "assistant"
    assert reply.text == "收到：你好"
    assert provider._session_id == "sess-42"  # noqa: SLF001 - 会话延续是协议的一部分


def test_unreachable_returns_down() -> None:
    provider = LegacyProvider("http://127.0.0.1:9", timeout_s=0.5)
    health = provider.health()
    assert health.state is HealthState.DOWN
    assert health.reason_code in {"PROVIDER_UNREACHABLE", "PROVIDER_BAD_RESPONSE"}


def test_history_empty_on_failure() -> None:
    provider = LegacyProvider("http://127.0.0.1:9", timeout_s=0.5)
    assert provider.history() == []
