from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mascot_core.update import install, source_kind


def _payload(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mascot.exe").write_bytes(b"exe")
    (root / "_internal").mkdir()
    (root / "_internal" / "data.txt").write_text("x", encoding="utf-8")
    return root


def _app(tmp_path: Path) -> Path:
    app = tmp_path / "local" / "mascot" / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app.parent / "current.txt").write_text("0.1.0\n", encoding="utf-8")
    return app


def test_source_kind_dir_needs_exe(tmp_path: Path) -> None:
    good = _payload(tmp_path / "dist")
    assert source_kind(good) == "dir"
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="mascot.exe"):
        source_kind(empty)


def test_source_kind_zip_and_reject_file(tmp_path: Path) -> None:
    z = tmp_path / "mascot.zip"
    z.write_bytes(b"PK")
    assert source_kind(z) == "zip"
    plain = tmp_path / "readme.txt"
    plain.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="目录或 .zip"):
        source_kind(plain)


def test_install_from_dir_switches_current(tmp_path: Path) -> None:
    app = _app(tmp_path)
    src = _payload(tmp_path / "dist")
    res = install(src, app, "0.2.0")
    assert res["installed"] is True
    assert res["previous"] == "0.1.0"
    assert (app / "0.2.0" / "mascot.exe").is_file()
    assert (app.parent / "current.txt").read_text(encoding="utf-8").strip() == "0.2.0"
    assert not list(app.glob(".incoming-*"))


def test_dry_run_touches_nothing(tmp_path: Path) -> None:
    app = _app(tmp_path)
    src = _payload(tmp_path / "dist")
    res = install(src, app, "0.2.0", dry_run=True)
    assert res["installed"] is False
    assert res["would_remove"] == []
    assert not (app / "0.2.0").exists()
    assert (app.parent / "current.txt").read_text(encoding="utf-8").strip() == "0.1.0"


def test_prune_keeps_two_after_upgrade(tmp_path: Path) -> None:
    app = _app(tmp_path)
    (app / "0.1.0").mkdir()
    (app / "0.1.0" / "mascot.exe").write_bytes(b"old")
    res = install(_payload(tmp_path / "d2"), app, "0.2.0", keep=2)
    assert (app / "0.2.0").is_dir()
    assert (app / "0.1.0").is_dir()
    res = install(_payload(tmp_path / "d3"), app, "0.3.0", keep=2)
    assert res["removed"] == ["0.1.0"]
    assert not (app / "0.1.0").exists()
    assert res["freed_bytes"] > 0


def test_existing_version_needs_force(tmp_path: Path) -> None:
    app = _app(tmp_path)
    src = _payload(tmp_path / "dist")
    install(src, app, "0.2.0")
    with pytest.raises(ValueError, match="--force"):
        install(src, app, "0.2.0")
    res = install(src, app, "0.2.0", force=True)
    assert res["installed"] is True


def test_bad_version_rejected(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with pytest.raises(ValueError, match="版本号"):
        install(_payload(tmp_path / "dist"), app, "../evil")


def test_install_from_zip_with_nested_folder(tmp_path: Path) -> None:
    app = _app(tmp_path)
    src = _payload(tmp_path / "pk" / "mascot")
    z = tmp_path / "mascot.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src.parent).as_posix())
    res = install(z, app, "0.2.0")
    assert res["kind"] == "zip"
    assert (app / "0.2.0" / "mascot.exe").is_file()
    assert (app / "0.2.0" / "_internal" / "data.txt").is_file()


def test_zip_slip_rejected(tmp_path: Path) -> None:
    app = _app(tmp_path)
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("mascot.exe", b"exe")
        zf.writestr("../escape.txt", b"pwn")
    with pytest.raises(ValueError, match="越界"):
        install(z, app, "0.2.0")
    assert not (tmp_path / "local" / "escape.txt").exists()
    assert not (app / "0.2.0").exists()
