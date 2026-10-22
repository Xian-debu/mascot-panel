"""M21：health 探测用独立的短超时（启动路径不被后端拖住）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mascot_app.providers import make_provider
from mascot_core.config import Settings


def test_default_health_timeout_is_short() -> None:
    settings = Settings(provider="legacy")
    assert settings.health_timeout_s == 0.8
    assert settings.health_timeout_s < settings.provider_timeout_s


def test_legacy_provider_gets_health_timeout() -> None:
    provider = make_provider(Settings(provider="legacy", health_timeout_s=0.3))
    assert provider.health_timeout_s == 0.3  # type: ignore[attr-defined]
    assert provider.timeout_s == 2.0  # type: ignore[attr-defined]


def test_auto_provider_propagates_health_timeout() -> None:
    provider = make_provider(Settings(provider="auto", health_timeout_s=0.5))
    assert provider._legacy.health_timeout_s == 0.5  # noqa: SLF001
    assert provider._wsl.health_timeout_s == 0.5  # noqa: SLF001


def test_health_timeout_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(health_timeout_s=0.0)
    with pytest.raises(ValidationError):
        Settings(health_timeout_s=20.0)
