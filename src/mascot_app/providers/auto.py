"""Auto provider：按后端实际提供的契约自动选路。

现有两种后端：

1. legacy：旧 deepseek-chat-rebuild 的 /api/pet/{status,news,ask}（新闻格式 + SSE），
   用户把旧服务跑起来就能真聊；
2. wsl：新契约 /api/pet/{health,history,send}，目前只有 scripts/dev-chat-backend.py 假后端实现。

默认 auto：先探 legacy（一个 GET /api/pet/status），不行再探 wsl。选中的后端记住，
history/send 都发给它，避免每条消息重新选路、也避免两套后端消息混在一条时间线。
"""

from __future__ import annotations

from collections.abc import Callable

from mascot_app.providers.legacy import LegacyProvider
from mascot_app.providers.wsl import WslProvider
from mascot_core.contract import HealthState, Message, ProviderHealth


class AutoProvider:
    name = "auto"

    def __init__(self, base_url: str, timeout_s: float = 2.0) -> None:
        self._legacy = LegacyProvider(base_url, timeout_s=timeout_s)
        self._wsl = WslProvider(base_url, timeout_s=timeout_s)
        self._active: LegacyProvider | WslProvider = self._legacy

    def health(self) -> ProviderHealth:
        legacy = self._legacy.health()
        if legacy.state is HealthState.UP:
            self._active = self._legacy
            return legacy
        fresh = self._wsl.health()
        if fresh.state is HealthState.UP:
            self._active = self._wsl
            return fresh
        legacy_detail = legacy.detail or legacy.reason_code or "未知"
        detail = f"legacy: {legacy_detail}"
        if fresh.detail and fresh.detail not in detail:
            detail += f"；新契约: {fresh.detail}"
        self._active = self._legacy
        return ProviderHealth(
            state=fresh.state,
            detail=detail,
            reason_code=fresh.reason_code or legacy.reason_code,
        )

    def history(self, limit: int = 50) -> list[Message]:
        return self._active.history(limit=limit)

    def send(self, text: str) -> Message:
        return self._active.send(text)

    def send_stream(self, text: str, on_delta: Callable[[str], None]) -> Message:
        """把流式能力转给当前选中的后端（legacy 是真流式，wsl 是单次交付）。"""
        stream = getattr(self._active, "send_stream", None)
        if callable(stream):
            return stream(text, on_delta)  # type: ignore[no-any-return]
        return self._active.send(text)

    def stop(self) -> None:
        return None
