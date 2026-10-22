"""AutoProvider 选路测试：legacy 优先，其次新契约，两者都挂时给出双方原因。"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mascot_app.providers.auto import AutoProvider
from mascot_core.contract import HealthState


def _serve(kind: str) -> tuple[ThreadingHTTPServer, str]:
    """kind: legacy | wsl。只实现对应契约，其它路径一律 404。"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if kind == "legacy" and self.path.startswith("/api/pet/status"):
                self._json({"status": "ok", "engine": "ready"})
                return
            if kind == "legacy" and self.path.startswith("/api/pet/news"):
                self._json({"code": 202000, "data": [{"id": 1, "title": "主人: 你好", "description": "你好"}]})
                return
            if kind == "wsl" and self.path.startswith("/api/pet/health"):
                self._json({"ok": True})
                return
            if kind == "wsl" and self.path.startswith("/api/pet/history"):
                self._json({"messages": [{"role": "assistant", "text": "新契约在", "ts": 1.0, "id": "new-1"}]})
                return
            self._json({"detail": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if kind == "legacy" and self.path.startswith("/api/pet/ask"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"data: legacy:{payload.get('message', '')}\n\n".encode())
                self.wfile.write(b"data: [SESSION:s1]\n\n")
                self.wfile.flush()
                return
            if kind == "wsl" and self.path.startswith("/api/pet/send"):
                self._json({"text": f"wsl:{payload.get('text', '')}"})
                return
            self._json({"detail": "not found"}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture()
def servers() -> Iterator[dict[str, tuple[ThreadingHTTPServer, str]]]:
    both = {"legacy": _serve("legacy"), "wsl": _serve("wsl")}
    try:
        yield both
    finally:
        for server, _url in both.values():
            server.shutdown()
            server.server_close()


def test_prefers_legacy_when_both_alive(servers) -> None:
    # legacy 服务对其他新契约路径返回 404，正好模拟“只有旧后端在跑”
    provider = AutoProvider(servers["legacy"][1], timeout_s=2.0)
    assert provider.health().state is HealthState.UP
    assert provider.history()[0].text == "你好"
    assert provider.send("在吗").text == "legacy:在吗"


def test_falls_back_to_new_contract(servers) -> None:
    url = servers["wsl"][1]
    provider = AutoProvider(url, timeout_s=1.0)
    assert provider.health().state is HealthState.UP
    assert provider.history()[0].text == "新契约在"
    assert provider.send("在吗").text == "wsl:在吗"


def test_both_down_reports_both_details() -> None:
    provider = AutoProvider("http://127.0.0.1:9", timeout_s=0.3)
    health = provider.health()
    assert health.state is HealthState.DOWN
    assert health.detail and "legacy:" in health.detail
