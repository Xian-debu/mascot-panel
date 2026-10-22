"""Provider 契约：Null / WSL 都必须满足 ChatProvider 的语义（失败必带 reason）。"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mascot_app.providers.null import NullProvider
from mascot_app.providers.wsl import WslProvider
from mascot_core.contract import ChatProvider, HealthState


def test_null_provider_implements_protocol() -> None:
    provider = NullProvider()
    assert isinstance(provider, ChatProvider)
    assert provider.name == "null"


def test_null_provider_is_explicitly_degraded() -> None:
    health = NullProvider().health()
    assert health.state is HealthState.DEGRADED
    assert health.reason_code == "PROVIDER_OFFLINE"
    assert health.ok is False


def test_null_provider_echoes_send_and_keeps_history() -> None:
    provider = NullProvider()
    sent = provider.send("你好")
    assert sent.role == "user"
    assert provider.history()[-1].text == "你好"


class _Handler(BaseHTTPRequestHandler):
    history = [
        {"role": "assistant", "text": "早，今天想做什么？", "ts": 1700000000.0, "id": "a1"},
        {"role": "user", "text": "看一下昨天的日志", "ts": 1700000010.0, "id": "u1"},
    ]

    def _json(self, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server 约定
        if self.path.startswith("/api/pet/health"):
            self._json({"ok": True})
        elif self.path.startswith("/api/pet/history"):
            self._json({"messages": self.history})
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/api/pet/send"):
            self._json({"text": f"收到：{payload.get('text', '')}"})
        else:
            self.send_error(404)

    def log_message(self, *args: object) -> None:
        return None


@pytest.fixture()
def fake_backend() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_wsl_provider_health_up(fake_backend: str) -> None:
    provider = WslProvider(base_url=fake_backend, timeout_s=2.0)
    assert isinstance(provider, ChatProvider)
    health = provider.health()
    assert health.state is HealthState.UP
    assert health.latency_ms is not None


def test_wsl_provider_history_and_send(fake_backend: str) -> None:
    provider = WslProvider(base_url=fake_backend, timeout_s=2.0)
    history = provider.history(limit=2)
    assert [m.role for m in history] == ["assistant", "user"]
    assert history[0].msg_id == "a1"
    reply = provider.send("在吗")
    assert reply.role == "assistant"
    assert reply.text == "收到：在吗"


def test_wsl_provider_reports_unreachable() -> None:
    """端口上没人时必须 DOWN + 明确 reason，绝不允许抛异常给 UI。"""
    provider = WslProvider(base_url="http://127.0.0.1:9", timeout_s=0.3)
    health = provider.health()
    assert health.state is HealthState.DOWN
    assert health.reason_code in {"PROVIDER_UNREACHABLE", "PROVIDER_BAD_RESPONSE"}


def test_wsl_provider_history_falls_back_to_empty() -> None:
    provider = WslProvider(base_url="http://127.0.0.1:9", timeout_s=0.3)
    assert provider.history() == []
