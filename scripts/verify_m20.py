"""M20 验收：历史条数可配置（history_limit，热字段）。

用临时配置（--config）+ 无宠物启动（null provider）：
1. history_limit=5 启动，快照里 settings.history_limit==5
2. 连发 8 条：state.json 与 history.json 都只留最近 5 条，且留的是最新的
3. 热改 history_limit=10（不重启）：下一个实例设置生效，新消息能留到第 6 条
4. 再热改回 5：内存与磁盘立刻被裁到 5 条
5. ctl stop 后退出码 0
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
HISTORY = STATE_DIR / "history.json"

BASE = "fps = 10\npoll_interval_ms = 200\nhistory_limit = 5\n"


def read_state() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def texts(snap: dict) -> list[str]:
    return [m.get("text", "") for m in snap.get("messages", [])]


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


def send(text: str, cfg: Path) -> dict:
    _code, out = cli("ctl", "send", "--text", text, "--config", str(cfg))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    checks: dict[str, object] = {}
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    for path in (STATE, HISTORY, STATE_DIR / "control.json"):
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
            checks["boot_limit_5"] = snap.get("settings", {}).get("history_limit") == 5
            checks["boot_no_reload"] = snap.get("config", {}).get("reloads") == 0

            sent_ok = True
            for i in range(1, 9):
                out = send(f"M20-{i}", cfg)
                sent_ok = sent_ok and out.get("ok") is True
                wait_for(lambda s, i=i: f"M20-{i}" in texts(s), 8)
            checks["sent_all"] = sent_ok
            snap = wait_for(lambda s: len(s.get("messages", [])) == 5, 10)
            got = texts(snap)
            checks["messages_capped"] = len(snap.get("messages", [])) == 5
            checks["keeps_latest"] = got[-1:] == ["M20-8"] and got[0] == "M20-4"
            with contextlib.suppress(Exception):
                disk = json.loads(HISTORY.read_text(encoding="utf-8"))
            checks["history_file_capped"] = len(disk.get("messages", [])) == 5

            code, out = cli("config", "set", "history_limit", "10", "--config", str(cfg))
            checks["grow_set_ok"] = code == 0 and out.get("data", {}).get("hot") is True
            snap = wait_for(lambda s: s.get("settings", {}).get("history_limit") == 10, 8)
            checks["grow_applied"] = snap.get("settings", {}).get("history_limit") == 10
            _out = send("M20-9", cfg)
            snap = wait_for(lambda s: len(s.get("messages", [])) == 6, 8)
            checks["grow_keeps_more"] = len(snap.get("messages", [])) == 6

            code, out = cli("config", "set", "history_limit", "5", "--config", str(cfg))
            checks["shrink_set_ok"] = code == 0 and out.get("data", {}).get("hot") is True
            snap = wait_for(lambda s: len(s.get("messages", [])) == 5, 8)
            checks["shrink_applied"] = len(snap.get("messages", [])) == 5
            checks["shrink_keeps_latest"] = texts(snap)[-1:] == ["M20-9"]
            with contextlib.suppress(Exception):
                disk = json.loads(HISTORY.read_text(encoding="utf-8"))
            checks["shrink_file_capped"] = len(disk.get("messages", [])) == 5
            checks["instance_alive"] = proc.poll() is None

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
