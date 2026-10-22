"""聊天后端 provider：auto（自动选路）/ legacy（旧契约）/ wsl（新契约）/ null（离线）。"""

from __future__ import annotations

from mascot_app.providers.auto import AutoProvider
from mascot_app.providers.legacy import LegacyProvider
from mascot_app.providers.null import NullProvider
from mascot_app.providers.wsl import WslProvider
from mascot_core.config import Settings
from mascot_core.contract import ChatProvider

__all__ = ["AutoProvider", "LegacyProvider", "NullProvider", "WslProvider", "make_provider"]


def make_provider(settings: Settings) -> ChatProvider:
    """按配置选 provider；未知名字回落到 Null（离线），不抛异常。"""
    name = settings.provider
    if name == "legacy":
        return LegacyProvider(
            base_url=settings.provider_base_url,
            timeout_s=settings.provider_timeout_s,
        )
    if name in ("auto", "wsl"):
        builder = AutoProvider if name == "auto" else WslProvider
        return builder(
            base_url=settings.provider_base_url,
            timeout_s=settings.provider_timeout_s,
        )
    return NullProvider()
