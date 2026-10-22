"""M19 验收：配置热重载（改 config.toml 不用重启）。

用临时配置文件（--config），无宠物启动（null provider）：
1. 启动时 fps=10，config.reloads=0
2. 配置没变时不会平白重载（等 2s 仍是 0）
3. 运行中 config set fps 30：状态里 fps 变 30、reloads 增加
4. 再改冷字段 pet_window_class：restart_required 里出现它
5. 非法值 fps=999 被 CLI 拒绝，实例不受影响
6. ctl stop 后退出码 0
"""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
STATE = STATE_DIR / "state.json"

BASE = "fps = 10\npoll_interval_ms = 200\n"


def read_state() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def wait_for(pred, timeout=20.0) -> dict:
    t0 = time.time()
    snap = read_state()
    while time.time() - t0 < timeout:
        snap = read_state()
        if pred(snap):
            return snap
        time.sleep(0.1)
    return snap


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return proc.returncode, json.loads(proc.stdout)
    return proc.returncode, {"raw": proc.stdout + proc.stderr}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    checks: dict[str, object] = {}
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    for path in (STATE, STATE_DIR / "control.json"):
        with contextlib.suppress(OSError):
            path.unlink()

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.toml"
        cfg.write_text(BASE, encoding="utf-8")
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "mascot_app.cli", "run",
                "--provider", "null", "--config", str(cfg),
            ],
            cwd=str(ROOT),
            env=env,
        )
        try:
            snap = wait_for(lambda s: s.get("state") == "idle", 30)
            checks["boot_fps_10"] = snap.get("settings", {}).get("fps") == 10
            checks["boot_no_reload"] = snap.get("config", {}).get("reloads") == 0
            checks["config_path_tracked"] = str(
                snap.get("config", {}).get("path", "")
            ).endswith("config.toml")

            time.sleep(2.0)
            snap = read_state()
            checks["idle_no_reload"] = snap.get("config", {}).get("reloads") == 0

            code, out = cli("config", "set", "fps", "30", "--config", str(cfg))
            checks["set_exit_0"] = code == 0 and out.get("ok") is True
            checks["set_marks_hot"] = out.get("data", {}).get("hot") is True and (
                out.get("data", {}).get("restart_required") is False
            )
            snap = wait_for(
                lambda s: s.get("settings", {}).get("fps") == 30
                and s.get("config", {}).get("reloads", 0) >= 1,
                8,
            )
            checks["fps_hot_applied"] = snap.get("settings", {}).get("fps") == 30
            checks["reload_counted"] = snap.get("config", {}).get("reloads", 0) >= 1
            checks["hot_not_restart"] = snap.get("config", {}).get("restart_required") == []

            code, out = cli("config", "set", "log_level", "DEBUG", "--config", str(cfg))
            checks["cold_set_exit_0"] = code == 0 and out.get("ok") is True
            checks["cold_set_marks_restart"] = out.get("data", {}).get("hot") is False and (
                out.get("data", {}).get("restart_required") is True
            )
            snap = wait_for(
                lambda s: "log_level" in s.get("config", {}).get("restart_required", []),
                8,
            )
            checks["cold_reports_restart"] = "log_level" in snap.get(
                "config", {}
            ).get("restart_required", [])
            checks["instance_alive"] = proc.poll() is None

            code, out = cli("config", "set", "fps", "999", "--config", str(cfg))
            checks["bad_value_rejected"] = code == 2
            time.sleep(1.5)
            checks["alive_after_bad_value"] = proc.poll() is None

            _code, res = cli("ctl", "stop", "--config", str(cfg))
            checks["stop_ok"] = res.get("ok") is True
            proc.wait(timeout=15)
            checks["exit_code"] = proc.returncode == 0
        finally:
            if proc.poll() is None:
                proc.kill()

    failed = [k for k, v in checks.items() if v is False]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
