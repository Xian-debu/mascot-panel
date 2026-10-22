"""状态目录解析（A3/M33）：MASCOT_STATE_DIR > %LOCALAPPDATA%/mascot > ~/.mascot。"""

from __future__ import annotations

from pathlib import Path

from mascot_core.paths import state_dir


def test_override_wins(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MASCOT_STATE_DIR", str(tmp_path / "dev"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    assert state_dir() == tmp_path / "dev"


def test_localappdata_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MASCOT_STATE_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    assert state_dir() == tmp_path / "appdata" / "mascot"


def test_home_fallback(monkeypatch) -> None:
    monkeypatch.delenv("MASCOT_STATE_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert state_dir() == Path.home() / ".mascot"


def test_override_expands_user(monkeypatch) -> None:
    monkeypatch.setenv("MASCOT_STATE_DIR", "~/mascot-dev")
    assert state_dir() == Path.home() / "mascot-dev"
