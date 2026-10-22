"""配置写回与运行态开关持久化。"""

from __future__ import annotations

from pathlib import Path

import pytest

from mascot_core import configfile


def test_set_and_read_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    configfile.set_config_value("provider", "legacy", path)
    configfile.set_config_value("fps", "20", path)
    configfile.set_config_value("panel_size", "360, 480", path)
    configfile.set_config_value("allow_offline", "false", path)

    data = configfile.read_config_file(path)
    assert data["provider"] == "legacy"
    assert data["fps"] == 20
    assert data["panel_size"] == [360, 480]
    assert data["allow_offline"] is False


def test_set_keeps_other_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    configfile.set_config_value("provider", "wsl", path)
    configfile.set_config_value("log_level", "DEBUG", path)
    assert configfile.read_config_file(path) == {"provider": "wsl", "log_level": "DEBUG"}
    assert configfile.read_config_file(path)["log_level"] == "DEBUG"


def test_unknown_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown config key"):
        configfile.set_config_value("nope", "1", tmp_path / "config.toml")
    assert not (tmp_path / "config.toml").exists()


@pytest.mark.parametrize("raw", ["abc", "2", ""])
def test_bad_boolean_rejected(tmp_path: Path, raw: str) -> None:
    with pytest.raises(ValueError):
        configfile.set_config_value("allow_offline", raw, tmp_path / "config.toml")


def test_out_of_range_rejected_by_settings(tmp_path: Path) -> None:
    # fps 有 Field(ge=1, le=60)，写盘前必须被 Settings 拦下
    with pytest.raises(ValueError):
        configfile.set_config_value("fps", "999", tmp_path / "config.toml")
    assert not (tmp_path / "config.toml").exists()


def test_unset_removes_key(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    configfile.set_config_value("fps", "12", path)
    assert configfile.unset_config_value("fps", path) is True
    assert configfile.unset_config_value("fps", path) is False
    assert "fps" not in configfile.read_config_file(path)


def test_env_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mascot_core.config import load_settings

    path = tmp_path / "config.toml"
    configfile.set_config_value("fps", "12", path)
    assert load_settings(path).fps == 12

    monkeypatch.setenv("MASCOT_FPS", "30")
    assert load_settings(path).fps == 30


def test_flag_persistence_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mascot_app import runtime

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert runtime.load_flags() == {}
    runtime.save_flags(dnd=True, paused=False)
    assert runtime.load_flags() == {"dnd": True, "paused": False}
    runtime.save_flags(dnd=False, paused=True)
    assert runtime._flags_path().is_file()
    assert runtime.load_flags() == {"dnd": False, "paused": True}


def test_corrupt_flags_file_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mascot_app import runtime

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = runtime._flags_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert runtime.load_flags() == {}


def test_runtime_starts_with_persisted_dnd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mascot_app import runtime
    from mascot_app.providers.null import NullProvider

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime.save_flags(dnd=True, paused=True)
    rt = runtime.Runtime(settings=runtime.Settings(), provider=NullProvider())
    snap = rt.snapshot()
    assert snap["dnd"] is True
    assert snap["paused"] is True
