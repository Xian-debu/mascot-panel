"""M9 验收：免打扰（DND）与面板定位。

- 启动（--provider null）→ 等 tracking
- ctl dnd on → snapshot.dnd=true 且面板不可见
- ctl to-ball / to-panel 不受影响（手动仍可打开）
- ctl dnd off → dnd=false
- ctl stop 退出
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = Path(__file__).resolve().parents[3] / "venv" / "Scripts" / "python.exe"
STATE = Path.home() / "AppData" / "Local" / "mascot" / "state.json"


def read_state() -> dict:
    for _ in range(50):
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            time.sleep(0.1)
    return {}


def wait_for(pred, timeout=25.0) -> dict:
    t0 = time.time()
    snap = {}
    while time.time() - t0 < timeout:
        snap = read_state()
        if pred(snap):
            return snap
        time.sleep(0.1)
    return snap


def ctl(*args: str) -> dict:
    exe = sys.executable
    proc = subprocess.run(
        [exe, "-m", "mascot_app.cli", "ctl", *args], capture_output=True, text=True, cwd=str(ROOT)
    )
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"ok": False, "raw": proc.stdout + proc.stderr}


def panel_visible() -> bool:
    from mascot_win import win32

    hwnd = win32.find_window("mascot-panel", timeout_s=0.5)
    return bool(hwnd) and win32.is_visible(hwnd)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    for p in (STATE, STATE.parent / "control.json"):
        with __import__("contextlib").suppress(OSError):
            p.unlink()
    proc = subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"], cwd=str(ROOT)
    )
    checks: dict[str, object] = {}
    try:
        snap = wait_for(lambda s: s.get("state") == "tracking" and s.get("pet"))
        checks["tracking"] = snap.get("state")
        wait_for(lambda _s: panel_visible(), 10)
        checks["panel_visible_before"] = panel_visible()

        ctl("dnd", "on")
        snap = wait_for(lambda s: s.get("dnd") is True)
        checks["dnd_on"] = snap.get("dnd")
        time.sleep(1.0)
        checks["panel_hidden_after_dnd"] = not panel_visible()

        ctl("to-ball")
        snap = wait_for(lambda s: s.get("state") == "orbital", 10)
        checks["manual_to_ball_works"] = snap.get("state")

        ctl("dnd", "off")
        snap = wait_for(lambda s: s.get("dnd") is False)
        checks["dnd_off"] = snap.get("dnd")

        ctl("to-panel")
        snap = wait_for(lambda s: s.get("state") == "tracking", 10)
        checks["manual_to_panel_works"] = snap.get("state")
        wait_for(lambda _s: panel_visible(), 8)
        checks["panel_visible_after"] = panel_visible()

        checks["ctl_stop"] = ctl("stop")
    finally:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    checks["process_exit"] = proc.returncode
    ok = (
        checks.get("tracking") == "tracking"
        and checks.get("panel_visible_before") is True
        and checks.get("dnd_on") is True
        and checks.get("panel_hidden_after_dnd") is True
        and checks.get("manual_to_ball_works") == "orbital"
        and checks.get("dnd_off") is False
        and checks.get("manual_to_panel_works") == "tracking"
        and checks.get("panel_visible_after") is True
        and checks.get("process_exit") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=1))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
