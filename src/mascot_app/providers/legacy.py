"""Legacy provider：对接旧 deepseek-chat-rebuild 的 /api/pet/* 契约。

旧后端是给 ASUS 原生桌宠写的：

    GET  /api/pet/status            -> {"status":"ok","engine":"ready"|"missing"|"error",...}
    GET  /api/pet/news?session_id=  -> {"code":202000,"data":[{id,title,description,...}]}
    POST /api/pet/ask {"message"}   -> text/event-stream，data: 分片，末条 [SESSION:<id>]

新面板的契约是 /api/pet/{health,history,send}。本适配层负责翻译：

- news item 的 title 前缀 "主人:" / "天选姬:" 决定 role；description 是正文；
- SSE 分片既拼成完整消息（send），也支持边收边回调（send_stream -> 面板流式渲染）；
- [SESSION:<id>] 存下来，下一轮 ask 带上，保持同一会话。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from mascot_core.contract import HealthState, Message, ProviderHealth

USER_PREFIXES = ("主人:", "主人：")


class LegacyProvider:
    name = "legacy"

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 2.0,
        send_timeout_s: float = 180.0,
        health_timeout_s: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.send_timeout_s = send_timeout_s
        # health 在启动路径上串行探测（auto 要连探两次），单独用更短超时。
        self.health_timeout_s = health_timeout_s if health_timeout_s is not None else timeout_s
        self._session_id = ""
        self._last_error = ""

    # ---- HTTP 基础 -------------------------------------------------------

    def _get(self, path: str, timeout: float | None = None) -> Any:
        req = urllib.request.Request(f"{self.base_url}{path}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(  # noqa: S310 - 本机回环
            req, timeout=self.timeout_s if timeout is None else timeout
        ) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health(self) -> ProviderHealth:
        started = time.monotonic()
        try:
            raw = self._get("/api/pet/status", timeout=self.health_timeout_s)
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
                detail="后端在线但引擎 " + engine + "（可能缺 API Key）",
                reason_code="PROVIDER_ENGINE_DOWN",
            )
        return ProviderHealth(state=HealthState.UP, latency_ms=ms)

    def history(self, limit: int = 50) -> list[Message]:
        path = "/api/pet/news"
        if self._session_id:
            path += "?session_id=" + urllib.parse.quote(self._session_id)
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
                    msg_id="legacy-" + str(item.get("id", idx)),
                )
            )
        return out[-limit:]

    def send(self, text: str) -> Message:
        """一次性发送（不关心中间分片）。"""
        return self.send_stream(text, lambda _piece: None)

    def send_stream(self, text: str, on_delta: Callable[[str], None]) -> Message:
        """POST /api/pet/ask，每收到一个 SSE 分片就回调 on_delta。

        on_delta 抛 SendCancelled 时中断读取并上抛；已收到的分片由调用方保存。
        """
        payload: dict[str, Any] = {"message": text}
        if self._session_id:
            payload["session_id"] = self._session_id
        req = urllib.request.Request(
            f"{self.base_url}/api/pet/ask",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        chunks: list[str] = []
        session_id = ""
        with urllib.request.urlopen(req, timeout=self.send_timeout_s) as resp:  # noqa: S310
            for raw_line in resp:
                # 只去行尾换行：SSE 分片自己可能以空格开头/结尾，strip() 会把词粘在一起
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                piece = line[5:]
                if piece.startswith(" "):
                    piece = piece[1:]
                if piece.startswith("[SESSION:"):
                    session_id = piece[len("[SESSION:") :].rstrip("]")  # noqa: E203
                    break
                if piece.startswith("[ERROR]"):
                    raise RuntimeError(piece)
                if piece == "[DONE]":
                    break
                chunks.append(piece)
                on_delta(piece)
        if session_id:
            self._session_id = session_id
        body = "".join(chunks).strip()
        if not body:
            raise RuntimeError("legacy 后端返回空回复")
        return Message(role="assistant", text=body, ts=time.time())

    def stop(self) -> None:
        return None
