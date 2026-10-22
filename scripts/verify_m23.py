"""M23 验收：mascot.exe update 就地升级（目录/zip、dry-run、prune、force）。

不用真安装目录：--app-dir 指到临时目录，源目录里放个假 mascot.exe 就够了
（update 只负责复制/切指针，不校验 exe 是不是真的桌宠）。
"""
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

EXE = "mascot.exe"
CHECKS: dict = {}


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    with contextlib.suppress(Exception):
        return proc.returncode, json.loads(proc.stdout)
    return proc.returncode, {"raw": (proc.stdout or "") + (proc.stderr or "")}


def payload(dirpath: Path, tag: str) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / EXE).write_bytes(("fake-" + tag).encode())
    (dirpath / "_internal").mkdir(exist_ok=True)
    (dirpath / "_internal" / "x.txt").write_text(tag, encoding="utf-8")
    return dirpath


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    base = Path(tempfile.mkdtemp(prefix="mascot-m23-"))
    app = base / "local" / "mascot" / "app"
    app.mkdir(parents=True)
    payload(app / "0.1.0", "old")
    (app.parent / "current.txt").write_text("0.1.0" + chr(10), encoding="utf-8")
    try:
        # 1) 目录升级：版本号从目录名推断（不传 --version）
        src2 = payload(base / "src" / "0.2.0", "v2")
        code, out = cli("update", "--from", str(src2), "--app-dir", str(app))
        data = out.get("data", {})
        CHECKS["dir_install_exit_0"] = code == 0 and out.get("ok") is True
        CHECKS["version_inferred_from_dir"] = data.get("version") == "0.2.0"
        CHECKS["installed_flag"] = data.get("installed") is True
        CHECKS["previous_reported"] = data.get("previous") == "0.1.0"
        CHECKS["current_switched"] = (app.parent / "current.txt").read_text(encoding="utf-8").strip() == "0.2.0"
        CHECKS["exe_copied"] = (app / "0.2.0" / EXE).is_file()
        CHECKS["old_version_kept"] = (app / "0.1.0").is_dir()

        # 2) 再装 0.3.0，keep=2 -> 0.1.0 被回收
        src3 = payload(base / "src" / "0.3.0", "v3")
        code, out = cli("update", "--from", str(src3), "--app-dir", str(app), "--keep", "2")
        data = out.get("data", {})
        CHECKS["upgrade_exit_0"] = code == 0 and data.get("installed") is True
        CHECKS["pruned_oldest"] = data.get("removed") == ["0.1.0"]
        CHECKS["freed_bytes"] = int(data.get("freed_bytes", 0)) > 0
        CHECKS["oldest_gone"] = not (app / "0.1.0").exists()

        # 3) dry-run：只报计划
        src4 = payload(base / "src" / "0.4.0", "v4")
        code, out = cli("update", "--from", str(src4), "--app-dir", str(app), "--dry-run")
        data = out.get("data", {})
        CHECKS["dry_run_exit_0"] = code == 0 and data.get("dry_run") is True
        CHECKS["dry_run_installed_false"] = data.get("installed") is False
        CHECKS["dry_run_lists_removal"] = data.get("would_remove") == ["0.2.0"]
        CHECKS["dry_run_no_dir"] = not (app / "0.4.0").exists()
        CHECKS["dry_run_current_unchanged"] = (app.parent / "current.txt").read_text(encoding="utf-8").strip() == "0.3.0"

        # 4) 同一版本再装要 --force
        code, out = cli("update", "--from", str(src3), "--app-dir", str(app))
        CHECKS["existing_needs_force"] = code == 2 and out.get("code") == "UPDATE_REJECTED"
        code, out = cli("update", "--from", str(src3), "--app-dir", str(app), "--force")
        CHECKS["force_overwrite_ok"] = code == 0 and out.get("data", {}).get("installed") is True

        # 5) zip 升级（多套一层目录）
        zsrc = payload(base / "pkg" / "mascot", "v5")
        zpath = base / "pkg" / "mascot.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            for p in sorted(zsrc.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(zsrc.parent).as_posix())
        code, out = cli(
            "update", "--from", str(zpath), "--version", "0.5.0", "--app-dir", str(app), "--keep", "2"
        )
        data = out.get("data", {})
        CHECKS["zip_install_ok"] = code == 0 and data.get("installed") is True and data.get("kind") == "zip"
        CHECKS["zip_exe_present"] = (app / "0.5.0" / EXE).is_file()
        CHECKS["zip_internal_present"] = (app / "0.5.0" / "_internal" / "x.txt").is_file()
        CHECKS["current_is_zip_version"] = (app.parent / "current.txt").read_text(encoding="utf-8").strip() == "0.5.0"

        # 6) 坏来源：明确报错、退出码 2
        code, out = cli("update", "--from", str(base / "nope"), "--app-dir", str(app))
        CHECKS["bad_source_exit_2"] = code == 2 and out.get("code") == "UPDATE_SOURCE"
        empty = base / "empty"
        empty.mkdir()
        code, out = cli("update", "--from", str(empty), "--app-dir", str(app))
        CHECKS["empty_dir_rejected"] = code == 2

        # 7) 收尾状态
        CHECKS["no_incoming_left"] = not list(app.glob(".incoming-*"))
        versions = sorted(p.name for p in app.iterdir() if p.is_dir())
        CHECKS["kept_two_versions"] = versions == ["0.3.0", "0.5.0"]
        CHECKS["listing_intact"] = len(versions) == 2
    finally:
        shutil.rmtree(base, ignore_errors=True)

    failed = [k for k, v in CHECKS.items() if v is False]
    print(json.dumps({"ok": not failed, "checks": CHECKS, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
