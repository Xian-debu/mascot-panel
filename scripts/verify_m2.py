"""M2 验收脚本：真的起进程、真的点球、真的停。

用法（Windows）：
    venv/Scripts/python.exe app/<ver>/scripts/verify_m2.py
退出码：0 = 全部通过；5 = 有检查失败。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mascot_win import win32  # noqa: E402


def state_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".mascot"
    return base / "mascot" if local else base


def read_state() -> dict:
    try:
        return json.loads((state_dir() / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wait_state(target: str, timeout: float, pid_holder: dict) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = read_state()
        if st.get("state") == target:
            return True
        if pid_holder.get("proc") is not None and pid_holder["proc"].poll() is not None:
            return False
        time.sleep(0.1)
    return False


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args], capture_output=True, text=True
    )
    try:
        return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return proc.returncode, {"raw": proc.stdout, "err": proc.stderr}


def find_ball() -> int:
    for hwnd in win32.enum_windows():
        if win32.get_class_name(hwnd).startswith("mascot_layered_"):
            return hwnd
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    checks: list[dict] = []
    win32.enable_dpi_awareness()
    proc = subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    holder = {"proc": proc}
    try:
        ok = wait_state("tracking", 20.0, holder)
        st = read_state()
        checks.append({"check": "follow_tracking", "ok": ok, "state": st.get("state"),
                       "pet": st.get("pet")})

        code, out = cli("ctl", "to-ball")
        ok2 = code == 0 and wait_state("orbital", 5.0, holder)
        checks.append({"check": "ctl_to_ball", "ok": ok2, "ctl": out})

        ball = find_ball()
        clicked = False
        if ball:
            win32._user32.PostMessageW(win32.wt.HWND(ball), win32.WM_LBUTTONDOWN, 1, 0)
            win32._user32.PostMessageW(win32.wt.HWND(ball), win32.WM_LBUTTONUP, 0, 0)
            clicked = wait_state("tracking", 5.0, holder)
        checks.append({"check": "click_ball_returns", "ok": clicked, "ball_hwnd": ball})

        code, out = cli("ctl", "status")
        running = out.get("data", {}).get("running") is True
        checks.append({"check": "ctl_status_running", "ok": running, "status": out.get("data", {}).get("state")})

        # 单实例：第二次启动必须被拒（exit 3, ALREADY_RUNNING）
        second = subprocess.run(
            [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
            capture_output=True, text=True, timeout=30,
        )
        dup_ok = second.returncode == 3 and "ALREADY_RUNNING" in second.stdout
        checks.append({"check": "single_instance", "ok": dup_ok, "rc": second.returncode})

        code, out = cli("ctl", "stop")
        stopped = False
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stopped = True
                break
            time.sleep(0.1)
        checks.append({"check": "ctl_stop", "ok": stopped and code == 0, "ctl": out})
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    all_ok = all(c["ok"] for c in checks)
    print(json.dumps({"ok": all_ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if all_ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
