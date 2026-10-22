#!/usr/bin/env python3
"""开发用假后端：实现 /api/pet/{health,history,send}，供 M4 面板联调。

真后端（WSL 侧的 agent 会话）还没接，这个脚本只用来验证"面板 → provider → HTTP"
这条链路通不通，顺便给截图/录屏用。不参与打包。

    python scripts/dev-chat-backend.py --port 8890
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HISTORY: list[dict[str, object]] = [
    {
        "role": "assistant",
        "text": "早上好，昨天的定时任务都跑完了。要不要看一下产物？",
        "ts": time.time() - 3600,
        "id": "seed-1",
    },
    {
        "role": "user",
        "text": "先看日志吧，代码块也要能渲染",
        "ts": time.time() - 3500,
        "id": "seed-2",
    },
    {
        "role": "assistant",
        "text": "好的，已按折叠显示，超过 12 行会收起来：\n\n```\ndef render(messages):\n    for m in messages:\n        print(m.role, m.text)\n```\n\n需要我贴完整输出吗？",
        "ts": time.time() - 3400,
        "id": "seed-3",
    },
]


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/pet/health"):
            self._json({"ok": True})
        elif self.path.startswith("/api/pet/history"):
            self._json({"messages": HISTORY[-50:]})
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not self.path.startswith("/api/pet/send"):
            self.send_error(404)
            return
        text = str(payload.get("text", ""))
        HISTORY.append({"role": "user", "text": text, "ts": time.time(), "id": f"u{len(HISTORY)}"})
        reply = f"（假后端）收到 {len(text)} 个字：{text[:40]}"
        HISTORY.append({"role": "assistant", "text": reply, "ts": time.time(), "id": f"a{len(HISTORY)}"})
        self._json({"text": reply})

    def log_message(self, fmt: str, *args: object) -> None:
        print("[fake-backend] " + (fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8890)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[fake-backend] http://{args.host}:{args.port}  (Ctrl-C 退出)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
