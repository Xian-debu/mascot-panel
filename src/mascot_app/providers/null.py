"""离线 provider：没有后端时面板仍然可用（读缓存、输入框可写、明示离线）。

旧实现在后端不可用时整块面板空白 30 秒，用户以为程序卡死。
"""

from __future__ import annotations

import time

from mascot_core.contract import HealthState, Message, ProviderHealth


class NullProvider:
    name = "null"

    def __init__(self, greeting: str = "离线模式：聊天后端不可用") -> None:
        self._greeting = greeting
        self._messages: list[Message] = [
            Message(role="assistant", text=greeting, ts=time.time(), msg_id="offline-0")
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            state=HealthState.DEGRADED,
            detail="no provider configured",
            reason_code="PROVIDER_OFFLINE",
        )

    def history(self, limit: int = 50) -> list[Message]:
        return self._messages[-limit:]

    def send(self, text: str) -> Message:
        msg = Message(role="user", text=text, ts=time.time(), msg_id=f"local-{len(self._messages)}")
        self._messages.append(msg)
        return msg

    def stop(self) -> None:
        return None
