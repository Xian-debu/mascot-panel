"""开发用假 legacy 后端：模拟旧 deepseek-chat-rebuild 的 /api/pet/* 契约。

用于本机验证 LegacyProvider/AutoProvider（不需要 API Key、不启动旧项目）：

    python scripts/dev-legacy-backend.py --port 8891
    python -m mascot_app.cli run --provider auto --provider-url http://127.0.0.1:8891

端点：
  GET  /api/pet/status  -> {"status":"ok","engine":"ready",...}
  GET  /api/pet/news    -> {"code":202000,"data":[{id,title,description,ts}]}
  POST /api/pet/ask     -> text/event-stream，data: 分片 ... data: [SESSION:<id>]
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEED: list[dict] = [
    {"id": 1, "title": "主人: 在吗", "description": "在吗"},
    {"id": 2, "title": "天选姬: 在的", "description": "在的~ 刚整理完今天的记录。"},
]


def _handler_factory(state: dict) -> type[BaseHTTPRequestHandler]:
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
            if self.path.startswith("/api/pet/status"):
                self._json(
                    {
                        "status": "ok",
                        "engine": "ready",
                        "sessions": 1,
                        "total_messages": len(state["items"]),
                    }
                )
                return
            if self.path.startswith("/api/pet/news"):
                self._json({"code": 202000, "data": state["items"]})
                return
            self._json({"detail": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            if not self.path.startswith("/api/pet/ask"):
                self._json({"detail": "not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            text = str(payload.get("message", ""))
            state["items"].append({"id": len(state["items"]) + 1, "title": f"主人: {text}", "description": text})
            reply = f"（假旧后端）收到 {len(text)} 个字：{text}"
            state["items"].append(
                {"id": len(state["items"]) + 1, "title": "天选姬: 回复", "description": reply}
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            for piece in ("（假旧后端）收到 ", f"{len(text)} 个字：{text}"):
                self.wfile.write(f"data: {piece}\n\n".encode())
            self.wfile.write(b"data: [SESSION:sess-dev]\n\n")
            self.wfile.flush()

    return Handler


def make_server(port: int = 0) -> ThreadingHTTPServer:
    state: dict = {"items": [dict(item) for item in SEED]}
    return ThreadingHTTPServer(("127.0.0.1", port), _handler_factory(state))


def serve_in_thread(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = make_server(port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="假 legacy 后端（开发用）")
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument("--stop-after", type=float, default=0.0, help="多少秒后自动退出（0=一直跑）")
    args = parser.parse_args(argv)
    server, url = serve_in_thread(args.port)
    print(json.dumps({"ok": True, "url": url}, ensure_ascii=False), flush=True)
    try:
        if args.stop_after > 0:
            time.sleep(args.stop_after)
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
