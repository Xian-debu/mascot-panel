"""M18 验收：已安装版本目录列举 / 回收 / 回滚目标。

全部在临时目录上做（--app-dir 显式路径），不碰真实安装：
1. versions 列出 app/ 下的版本目录，标出 current，含大小
2. --prune --dry-run 只报告不删除
3. 真 prune --keep 2 删旧留新，current 必留
4. keep 1 且 current 是最旧版本时，current 不被删
5. 非版本目录（backup/）不被当成版本、不被删
6. 真实安装目录里 current 与 current.txt 一致
"""
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", "versions", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return proc.returncode, json.loads(proc.stdout)
    return proc.returncode, {"raw": proc.stdout + proc.stderr}


def make_version(root: Path, name: str, size: int = 16) -> Path:
    d = root / "app" / name
    d.mkdir(parents=True)
    (d / "mascot.exe").write_bytes(b"x" * size)
    return d


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_version(root, "0.1.0", 8)
        make_version(root, "0.2.0", 16)
        make_version(root, "0.3.0", 32)
        (root / "app" / "backup").mkdir()
        (root / "app" / "backup" / "old.txt").write_text("keep", encoding="utf-8")
        (root / "current.txt").write_text("0.3.0", encoding="utf-8")
        app = root / "app"

        code, out = cli("--app-dir", str(app))
        data = out.get("data", {})
        rows = data.get("versions", [])
        checks["list_exit_0"] = code == 0 and out.get("ok") is True
        checks["list_versions"] = [r.get("version") for r in rows] == ["0.3.0", "0.2.0", "0.1.0"]
        checks["current_marked"] = [r.get("version") for r in rows if r.get("current")] == ["0.3.0"]
        checks["sizes_listed"] = [r.get("size_bytes") for r in rows] == [32, 16, 8]
        checks["backup_not_listed"] = "backup" not in [r.get("version") for r in rows]

        code, out = cli("--app-dir", str(app), "--prune", "--dry-run", "--keep", "2")
        prune = out.get("data", {}).get("prune", {})
        checks["dry_run_reports"] = prune.get("removed") == ["0.1.0"] and prune.get("dry_run") is True
        checks["dry_run_keeps_dirs"] = (app / "0.1.0").is_dir() and (app / "0.3.0").is_dir()
        checks["dry_run_freed"] = prune.get("freed_bytes") == 8

        code, out = cli("--app-dir", str(app), "--prune", "--keep", "2")
        prune = out.get("data", {}).get("prune", {})
        checks["real_prune_exit_0"] = code == 0 and prune.get("dry_run") is False
        checks["real_prune_removed"] = prune.get("removed") == ["0.1.0"]
        checks["real_prune_dirs"] = sorted(p.name for p in app.iterdir()) == [
            "0.2.0",
            "0.3.0",
            "backup",
        ]
        checks["backup_survived"] = (app / "backup" / "old.txt").read_text(encoding="utf-8") == "keep"

        # current 是最旧版本时也不许删（keep=1 只能删更新的）
        shutil.rmtree(app / "0.3.0")
        (root / "current.txt").write_text("0.2.0", encoding="utf-8")
        make_version(root, "0.4.0", 4)
        code, out = cli("--app-dir", str(app), "--prune", "--keep", "1")
        prune = out.get("data", {}).get("prune", {})
        checks["current_never_deleted"] = prune.get("removed") == ["0.4.0"] and (app / "0.2.0").is_dir()

        # 真实安装目录：current.txt 与列举结果一致（缺安装则跳过，记为 None）
        local = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        if local and (local / "app").is_dir():
            code, out = cli("--app-dir", str(local / "app"))
            data = out.get("data", {})
            cur = (local / "current.txt").read_text(encoding="utf-8").strip()
            checks["real_install_current"] = data.get("current") == cur
            checks["real_install_total"] = data.get("total_bytes", 0) > 0
        else:
            checks["real_install_current"] = None
            checks["real_install_total"] = None

    failed = [k for k, v in checks.items() if v is False]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
