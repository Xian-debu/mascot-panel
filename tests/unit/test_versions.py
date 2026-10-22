"""已安装版本目录的列举/回收（纯逻辑）。"""

from __future__ import annotations

from pathlib import Path

from mascot_core import versions


def _mk(root: Path, name: str, payload: bytes = b"x" * 10) -> Path:
    d = root / "app" / name
    d.mkdir(parents=True)
    (d / "mascot.exe").write_bytes(payload)
    return d


def test_is_version_name() -> None:
    for good in ("0.1.0", "1.2", "2.0.0-beta.1", "1.0.0+local"):
        assert versions.is_version_name(good), good
    for bad in ("app", "0.1.0.tmp", "v1.0", "", "..", "1.0 0"):
        assert not versions.is_version_name(bad), bad


def test_version_key_orders_numerically() -> None:
    names = ["0.9.0", "0.10.0", "0.2.1", "1.0"]
    assert sorted(names, key=versions.version_key) == ["0.2.1", "0.9.0", "0.10.0", "1.0"]


def test_list_versions_marks_current(tmp_path: Path) -> None:
    _mk(tmp_path, "0.1.0", b"a" * 5)
    _mk(tmp_path, "0.2.0", b"b" * 7)
    (tmp_path / "current.txt").write_text("0.2.0\n", encoding="utf-8")
    (tmp_path / "app" / "notes").mkdir()  # 非版本目录应被忽略
    rows = versions.list_versions(tmp_path / "app")
    assert [row["version"] for row in rows] == ["0.2.0", "0.1.0"]
    assert rows[0]["current"] is True and rows[1]["current"] is False
    assert rows[0]["size_bytes"] == 7 and rows[1]["size_bytes"] == 5


def test_list_versions_missing_dir(tmp_path: Path) -> None:
    assert versions.list_versions(tmp_path / "nope") == []


def test_pick_prune_keeps_current_and_newest() -> None:
    rows = [{"version": n} for n in ("0.1.0", "0.2.0", "0.3.0", "0.4.0")]
    assert versions.pick_prune(rows, keep=2, current="0.4.0") == ["0.2.0", "0.1.0"]
    assert versions.pick_prune(rows, keep=2, current="0.1.0") == ["0.3.0", "0.2.0"]
    assert versions.pick_prune(rows, keep=9, current="0.1.0") == []


def test_pick_prune_keep_one_still_keeps_current() -> None:
    rows = [{"version": n} for n in ("0.1.0", "0.2.0")]
    assert versions.pick_prune(rows, keep=1, current="0.1.0") == ["0.2.0"]


def test_prune_dry_run_does_not_delete(tmp_path: Path) -> None:
    _mk(tmp_path, "0.1.0")
    _mk(tmp_path, "0.2.0")
    (tmp_path / "current.txt").write_text("0.2.0", encoding="utf-8")
    out = versions.prune_versions(tmp_path / "app", keep=1, dry_run=True)
    assert out["removed"] == ["0.1.0"] and out["dry_run"] is True
    assert (tmp_path / "app" / "0.1.0").is_dir()


def test_prune_removes_old_and_keeps_current(tmp_path: Path) -> None:
    _mk(tmp_path, "0.1.0")
    _mk(tmp_path, "0.2.0")
    _mk(tmp_path, "0.3.0")
    (tmp_path / "current.txt").write_text("0.3.0", encoding="utf-8")
    out = versions.prune_versions(tmp_path / "app", keep=2, dry_run=False)
    assert out["removed"] == ["0.1.0"]
    assert out["kept"] == ["0.3.0", "0.2.0"]
    assert sorted(p.name for p in (tmp_path / "app").iterdir()) == ["0.2.0", "0.3.0"]


def test_prune_ignores_foreign_dirs(tmp_path: Path) -> None:
    _mk(tmp_path, "0.1.0")
    (tmp_path / "app" / "backup").mkdir()
    (tmp_path / "current.txt").write_text("0.1.0", encoding="utf-8")
    out = versions.prune_versions(tmp_path / "app", keep=1, dry_run=False)
    assert out["removed"] == []
    assert (tmp_path / "app" / "backup").is_dir()
