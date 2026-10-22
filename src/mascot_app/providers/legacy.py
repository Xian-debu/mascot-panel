"""Legacy provider：对接旧 deepseek-chat-rebuild 的 /api/pet/* 契约。

旧后端（/root/projects/deepseek-chat-rebuild）是给 ASUS 原生桌宠写的：

    GET  /api/pet/status             -> {"status":"ok", ...}            健康 + 会话统计
    GET  /api/pet/news?session_id=   -> {"code":202000,"data":[news...]} 会话历史（新闻格式）
    POST /api/pet/ask    {"message"} -> text/event-stream，data: 分片，末条 [SESSION:<id>]

新面板的契约是 /api/pet/{health,history,send}（见 mascot_core.contract）。本适配层负责翻译：
- news item 的 title 前缀 "主人:" / "天选姬:" 决定 role；description 是正文；
- 流式 SSE 拼接成一条 assistant 消息（本版不做增量渲染，避免面板协议改动）；
- [SESSION:<id>] 存下来，下一轮 ask 带上，保持同一会话。

这样用户把旧后端跑起来就能真聊，不必改旧项目一行代码。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mascot_core.contract import HealthState, Message, ProviderHealth

USER_PREFIXES = ("主人:", "主人：")


class LegacyProvider:
    name = "legacy"

    def __init__(self, base_url: str, timeout_s: float = 2.0, send_timeout_s: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.send_timeout_s = send_timeout_s
        self._session_id = ""
        self._last_error = ""

    # ---- HTTP 基础 -------------------------------------------------------

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(
            f"{self.base_url}{path}", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - 本机回环
            return json.loads(resp.read().decode("utf-8"))

    def health(self) -> ProviderHealth:
        started = time.monotonic()
        try:
            raw = self._get("/api/pet/status")
            ms = int((time.monotonic() - started) * 1000)
        except urllib.error.URLError as exc:
            self._last_error = str(getattr(exc, "reason", exc))
            return ProviderHealth(
                state=HealthState.DOWN, detail=self._last_error, reason_code="PROVIDER_UNREACHABLE"
            )
        except (TimeoutError, json.JSONDecodeError) as exc:
            self._last_error = str(exc)
            return ProviderHealth(
                state=HealthState.DOWN, detail=self._last_error, reason_code="PROVIDER_BAD_RESPONSE"
            )
        if not isinstance(raw, dict) or raw.get("status") != "ok":
            detail = json.dumps(raw, ensure_ascii=False)[:120] if isinstance(raw, dict) else "bad json"
            self._last_error = detail
            return ProviderHealth(
                state=HealthState.DEGRADED, detail=detail, reason_code="PROVIDER_BAD_RESPONSE"
            )
        engine = str(raw.get("engine", ""))
        if engine in ("missing", "error"):
            return ProviderHealth(
                state=HealthState.DEGRADED,
                latency_ms=ms,
                detail=f"后端在线但引擎 {engine}（可能缺 API Key）",
                reason_code="PROVIDER_ENGINE_DOWN",
            )
        return ProviderHealth(state=HealthState.UP, latency_ms=ms)

    def history(self, limit: int = 50) -> list[Message]:
        path = "/api/pet/news"
        if self._session_id:
            path += f"?session_id={urllib.parse.quote(self._session_id)}"
        try:
            raw = self._get(path)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return []
        items = raw.get("data", []) if isinstance(raw, dict) else []
        now = time.time()
        out: list[Message] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", ""))
            text = str(item.get("description", "")).strip()
            if not text:
                continue
            role = "user" if title.startswith(USER_PREFIXES) else "assistant"
            out.append(
                Message(
                    role=role,
                    text=text,
                    ts=now - (len(items) - idx) * 0.001,
                    msg_id=f"legacy-{item.get('id', idx)}",
                )
            )
        return out[-limit:]

    def send(self, text: str) -> Message:
        """POST /api/pet/ask，把 SSE 分片拼成一条消息。"""
        payload: dict[str, Any] = {"message": text}
        if self._session_id:
            payload["session_id"] = self._session_id
        req = urllib.request.Request(
            f"{self.base_url}/api/pet/ask",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        chunks: list[str] = []
        session_id = ""
        with urllib.request.urlopen(req, timeout=self.send_timeout_s) as resp:  # noqa: S310
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                piece = line[6:]
                if piece.startswith("[SESSION:"):
                    session_id = piece[len("[SESSION:") :].rstrip("]")
                    break
                if piece.startswith("[ERROR]"):
                    raise RuntimeError(piece)
                if piece == "[DONE]":
                    break
                chunks.append(piece)
        if session_id:
            self._session_id = session_id
        body = "".join(chunks).strip()
        if not body:
            raise RuntimeError("legacy 后端返回空回复")
        return Message(role="assistant", text=body, ts=time.time())

    def stop(self) -> None:
        return None
