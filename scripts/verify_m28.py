"""M28 验收：待机球双击时间窗可配置（click_window_ms），0 = 单击立即开面板。

无宠物启动（null provider）：
1. config set click_window_ms 0 后启动，snapshot.settings.click_window_ms == 0
2. 单击待机球：面板很快打开（3 次取最快，避开首次点击预热）
3. 热改回 350（hot=true）后无需重启，snapshot 同步
4. 单击待机球：明显要等一个时间窗（>=250ms）才打开
5. ctl stop → 退出码 0
"""
import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
)
STATE = STATE_DIR / "state.json"


def read_state() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def wait_for(pred, timeout=25.0) -> dict:
    t0 = time.time()
    snap = {}
    while time.time() - t0 < timeout:
        snap = read_state()
        if pred(snap):
            return snap
        time.sleep(0.01)
    return snap


def ctl(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", "ctl", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return json.loads(proc.stdout)
    return {"ok": False, "raw": proc.stdout + proc.stderr}


def config(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", "config", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return json.loads(proc.stdout)
    return {"ok": False, "raw": proc.stdout + proc.stderr}


def spawn() -> subprocess.Popen:
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    return subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        cwd=str(ROOT),
        env=env,
    )


def find_ball(win32) -> int:
    for h in win32.enum_windows():
        if win32.get_class_name(h).startswith("mascot_layered_") and win32.is_visible(h):
            return h
    return 0


def click(win32, x: int, y: int) -> float:
    """点一下，返回松手的时刻（秒）。"""
    win32.set_cursor_pos(x, y)
    time.sleep(0.15)
    win32.mouse_left(True)
    time.sleep(0.05)
    win32.mouse_left(False)
    return time.time()


def measure_open(win32, ball: int, attempts: int = 3) -> float:
    """重复「收进小球 → 点一下 → 等 idle_open」，返回最快的一次（秒）。"""
    best = 99.0
    for _ in range(attempts):
        ctl("to-ball")
        wait_for(lambda s: s.get("state") == "idle", 8)
        time.sleep(0.4)
        bx, by, bw, bh = win32.get_window_rect(ball)
        t0 = click(win32, bx + bw // 2, by + bh // 2)
        snap = wait_for(lambda s: s.get("state") == "idle_open", 6)
        if snap.get("state") == "idle_open":
            best = min(best, time.time() - t0)
    return round(best, 3)


def stop(proc: subprocess.Popen) -> int:
    ctl("stop")
    try:
        return proc.wait(timeout=12)
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from mascot_win import win32

    win32.enable_dpi_awareness()
    for path in (STATE, STATE_DIR / "control.json"):
        with contextlib.suppress(OSError):
            path.unlink()
    config("set", "click_window_ms", "0")

    checks: dict[str, object] = {}
    proc = spawn()
    try:
        snap = wait_for(lambda s: s.get("state") == "idle", 30)
        checks["state_idle"] = snap.get("state") == "idle"
        checks["click_window_setting"] = snap.get("settings", {}).get("click_window_ms")
        time.sleep(1.2)
        ball = find_ball(win32)
        checks["ball_visible"] = bool(ball)
        if not ball:
            raise SystemExit(5)

        # 1) 0 毫秒：单击不再等双击窗口
        checks["open_delay_zero_ms"] = measure_open(win32, ball)
        checks["zero_window_fast"] = float(checks["open_delay_zero_ms"]) < 0.35

        # 2) 热改回 350：不需要重启
        ctl("to-ball")
        wait_for(lambda s: s.get("state") == "idle", 8)
        time.sleep(0.3)
        resp = config("set", "click_window_ms", "350")
        checks["hot"] = resp.get("data", {}).get("hot") if isinstance(resp, dict) else None
        snap = wait_for(lambda s: s.get("settings", {}).get("click_window_ms") == 350, 8)
        checks["setting_reloaded"] = snap.get("settings", {}).get("click_window_ms") == 350

        # 3) 350 毫秒：单击要等时间窗过去才开面板
        checks["open_delay_default_ms"] = measure_open(win32, ball)
        checks["opens_after_window"] = (
            float(checks["open_delay_default_ms"]) >= 0.25
        )
    finally:
        checks["exit_code"] = stop(proc)
        config("unset", "click_window_ms")

    ok = (
        checks.get("state_idle") is True
        and checks.get("click_window_setting") == 0
        and checks.get("ball_visible") is True
        and checks.get("zero_window_fast") is True
        and checks.get("setting_reloaded") is True
        and checks.get("opens_after_window") is True
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
