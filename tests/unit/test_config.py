from __future__ import annotations

from pathlib import Path

from mascot_core.config import Settings, load_settings


def test_defaults() -> None:
    s = Settings()
    assert s.panel_size == (340, 460)
    assert s.follow_offset == (210, -130)
    assert s.lost_frames == 3
    assert s.ball_ratio == 0.34
    assert s.provider == "deepseek"
    assert s.provider_base_url == "https://api.deepseek.com"
    assert s.provider_model == "deepseek-chat"


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("MASCOT_FPS", "20")
    monkeypatch.setenv("MASCOT_PROVIDER", "null")
    s = Settings()
    assert s.fps == 20
    assert s.provider == "null"


def test_load_settings_reads_toml(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('fps = 24\nprovider = "null"\n', encoding="utf-8")
    s = load_settings(cfg)
    assert s.fps == 24
    assert s.provider == "null"


def test_load_settings_missing_file_uses_defaults(tmp_path: Path) -> None:
    s = load_settings(tmp_path / "nope.toml")
    assert s.fps == 10
