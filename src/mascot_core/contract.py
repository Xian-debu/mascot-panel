"""ChatProvider 协议：面板与"聊天后端"之间唯一的缝。

旧实现里，面板直接 fetch WSL 上的 /api/pet/*，后端挂了就静默 30 秒。
新实现把后端抽象成 provider：健康态是一等公民，失败必带 reason。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class HealthState(StrEnum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    state: HealthState
    detail: str = ""
    latency_ms: int | None = None
    reason_code: str = ""

    @property
    def ok(self) -> bool:
        return self.state is HealthState.UP


@dataclass(frozen=True, slots=True)
class Message:
    role: str  # "user" | "assistant"
    text: str
    ts: float = 0.0
    msg_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"role": self.role, "text": self.text, "ts": self.ts, "id": self.msg_id}


@dataclass(frozen=True, slots=True)
class SessionSummary:
    session_id: str
    title: str = ""
    unread: int = 0
    messages: tuple[Message, ...] = field(default_factory=tuple)


@runtime_checkable
class ChatProvider(Protocol):
    """实现者只需这五个方法；UI 不知道后面是 WSL、HTTP 还是 Null。"""

    name: str

    def health(self) -> ProviderHealth: ...

    def history(self, limit: int = 50) -> list[Message]: ...

    def send(self, text: str) -> Message: ...

    def stop(self) -> None: ...
