"""聊天后端 provider：WSL HTTP / 离线 Null，二者实现同一协议。"""

from __future__ import annotations

from mascot_app.providers.null import NullProvider
from mascot_app.providers.wsl import WslProvider
from mascot_core.config import Settings
from mascot_core.contract import ChatProvider

__all__ = ["NullProvider", "WslProvider", "make_provider"]


def make_provider(settings: Settings) -> ChatProvider:
    """按配置选 provider；未知名字回落到 Null（离线），不抛异常。"""
    if settings.provider == "wsl":
        return WslProvider(
            base_url=settings.provider_base_url,
            timeout_s=settings.provider_timeout_s,
        )
    return NullProvider()
