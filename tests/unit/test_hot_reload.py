"""热重载：merge_hot 的字段划分。"""

from __future__ import annotations

from mascot_core.config import HOT_FIELDS, Settings, merge_hot


def test_hot_fields_applied() -> None:
    old = Settings(fps=10, orbit_speed=1.0)
    new = Settings(fps=30, orbit_speed=2.5)
    merged, restart = merge_hot(old, new)
    assert merged.fps == 30 and merged.orbit_speed == 2.5
    assert restart == []
    assert old.fps == 10  # 不就地改旧对象


def test_cold_field_reports_restart() -> None:
    old = Settings(panel_size=(340, 460), provider="null")
    new = Settings(panel_size=(400, 500), provider="null")
    merged, restart = merge_hot(old, new)
    assert merged.panel_size == (340, 460)
    assert restart == ["panel_size"]


def test_provider_change_needs_restart() -> None:
    old = Settings(provider="null")
    new = Settings(provider="legacy")
    merged, restart = merge_hot(old, new)
    assert merged.provider == "null"
    assert "provider" in restart


def test_hot_fields_all_exist() -> None:
    names = set(type(Settings()).model_fields)
    assert set(HOT_FIELDS) <= names


def test_merged_is_same_type() -> None:
    merged, _ = merge_hot(Settings(), Settings(fps=20))
    assert isinstance(merged, Settings)


def test_history_limit_is_hot() -> None:
    merged, restart = merge_hot(Settings(history_limit=50), Settings(history_limit=5))
    assert merged.history_limit == 5
    assert restart == []


def test_history_limit_bounds() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(history_limit=2)
    with pytest.raises(ValidationError):
        Settings(history_limit=501)
