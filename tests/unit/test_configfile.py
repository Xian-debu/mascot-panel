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


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_set_preserves_comments_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "# 我的手写配置\n"
        "fps = 12  # 流畅优先\n"
        "\n"
        "# 下面这个键 mascot 不认，但别给我删了\n"
        "custom_thing = \"keep me\"\n"
        "\n"
        "[extra]\n"
        "note = \"表里的东西也别动\"\n",
        encoding="utf-8",
    )

    configfile.set_config_value("fps", "20", path)
    text = _text(path)
    assert "# 我的手写配置" in text
    assert "# 流畅优先" in text
    assert "fps = 20  # 流畅优先" in text
    assert "custom_thing = \"keep me\"" in text
    assert "[extra]" in text
    assert "note = \"表里的东西也别动\"" in text

    import tomllib

    data = tomllib.loads(text)
    assert data["fps"] == 20
    assert data["custom_thing"] == "keep me"
    assert data["extra"]["note"] == "表里的东西也别动"


def test_new_key_goes_before_first_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("fps = 12\n\n[extra]\nnote = \"x\"\n", encoding="utf-8")
    configfile.set_config_value("log_level", "DEBUG", path)
    text = _text(path)
    assert text.index("log_level") < text.index("[extra]")
    import tomllib

    data = tomllib.loads(text)
    assert data["log_level"] == "DEBUG"
    assert data["extra"]["note"] == "x"


def test_duplicate_key_lines_collapse(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    # tomllib 拒绝重复键，重复只可能出现在手改坏的文件里，所以走 write_config_file 修
    path.write_text("fps = 10\nfps = 12\n", encoding="utf-8")
    configfile.write_config_file({"fps": 18}, path)
    text = _text(path)
    assert text.count("fps =") == 1
    assert "fps = 18" in text


def test_write_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("# 注释\nfps = 12  # 尾注释\n", encoding="utf-8")
    configfile.write_config_file({"fps": 20}, path)
    first = _text(path)
    configfile.write_config_file({"fps": 20}, path)
    assert _text(path) == first


def test_set_on_missing_file_creates_header(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    configfile.set_config_value("fps", "15", path)
    text = _text(path)
    assert text.startswith("# mascot 配置")
    assert "fps = 15" in text


def test_unset_keeps_surrounding_comments(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("# 前\nfps = 12  # 行尾\n# 后\n", encoding="utf-8")
    assert configfile.unset_config_value("fps", path) is True
    text = _text(path)
    assert "fps" not in text
    assert "# 前" in text and "# 后" in text


def test_hash_inside_string_is_not_a_comment(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("provider = \"a#b\"\n", encoding="utf-8")
    configfile.set_config_value("provider", "legacy", path)
    text = _text(path)
    assert text.strip() == "provider = \"legacy\""


def test_load_settings_reads_commented_file(tmp_path: Path) -> None:
    from mascot_core.config import load_settings

    path = tmp_path / "config.toml"
    path.write_text("# 注释\nfps = 12  # 行尾\n", encoding="utf-8")
    configfile.set_config_value("allow_offline", "false", path)
    settings = load_settings(path)
    assert settings.fps == 12
    assert settings.allow_offline is False
