"""WSL provider：直连 127.0.0.1:8890 的 /api/pet/* 接口。

要点（全部来自旧实现踩雷）：
- 探测超时必须短（默认 2s），否则面板启动被后端拖死；
- 失败必须带 reason_code，让 UI 能显示"为什么离线"；
- 不在这里启动 WSL（拉起发行版是另一件事，M1 之后用 argv 数组做，绝不拼 shell）。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from mascot_core.contract import HealthState, Message, ProviderHealth


class WslProvider:
    name = "wsl"

    def __init__(self, base_url: str, timeout_s: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._last_error = ""

    def _get(self, path: str) -> object:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - 本机回环
            return json.loads(resp.read().decode("utf-8"))

    def health(self) -> ProviderHealth:
        started = time.monotonic()
        try:
            self._get("/api/pet/health")
            ms = int((time.monotonic() - started) * 1000)
            return ProviderHealth(state=HealthState.UP, latency_ms=ms)
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

    def history(self, limit: int = 50) -> list[Message]:
        try:
            raw = self._get(f"/api/pet/history?limit={limit}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return []
        items = raw.get("messages", []) if isinstance(raw, dict) else []
        return [
            Message(
                role=str(item.get("role", "assistant")),
                text=str(item.get("text", "")),
                ts=float(item.get("ts", 0.0)),
                msg_id=str(item.get("id", "")),
            )
            for item in items
        ]

    def send(self, text: str) -> Message:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/pet/send",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return Message(role="assistant", text=str(data.get("text", "")), ts=time.time())

    def stop(self) -> None:
        return None
