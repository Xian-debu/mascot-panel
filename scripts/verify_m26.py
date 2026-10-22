"""M26 验收：启动时面板窗口真的不可见（且不拦截点击），需要时才显示。

无宠物启动（null provider）：
1. 启动 6s 后能找到面板窗口 hwnd，但它 IsWindowVisible=false 且 WS_VISIBLE 位为 0
2. 面板窗口即使存在也不拦截它所在区域的点击（WindowFromPoint != 面板 hwnd）
3. 再等 2s 仍然隐藏（没有后续 Show）
4. 点待机球：state=idle_open、面板真的显示出来
5. ctl to-ball：面板又被藏回去
6. ctl stop → 退出码 0
"""
import contextlib
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
)
STATE = STATE_DIR / "state.json"
PANEL_TITLE = "mascot-panel"
GWL_STYLE = -16
WS_VISIBLE = 0x10000000


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
        time.sleep(0.1)
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


def spawn() -> subprocess.Popen:
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    return subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        cwd=str(ROOT),
        env=env,
    )


def ws_visible(hwnd: int) -> bool:
    style = ctypes.windll.user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE)
    return bool(style & WS_VISIBLE)


def window_from_point(x: int, y: int) -> int:
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.restype = wintypes.HWND
    hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
    return int(hwnd) if hwnd else 0


def find_ball(win32) -> int:
    for h in win32.enum_windows():
        if win32.get_class_name(h).startswith("mascot_layered_") and win32.is_visible(h):
            return h
    return 0


def click(win32, x: int, y: int) -> None:
    win32.set_cursor_pos(x, y)
    time.sleep(0.15)
    win32.mouse_left(True)
    time.sleep(0.05)
    win32.mouse_left(False)


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

    checks: dict[str, object] = {}
    proc = spawn()
    try:
        wait_for(lambda s: s.get("state") == "idle", 30)
        time.sleep(6.0)

        panel = win32.find_window(PANEL_TITLE, timeout_s=10.0)
        checks["panel_hwnd_found"] = bool(panel)
        if panel:
            px, py, pw, ph = win32.get_window_rect(panel)
            checks["panel_rect"] = [px, py, pw, ph]
            checks["panel_is_visible_api"] = win32.is_visible(panel)
            checks["panel_ws_visible"] = ws_visible(panel)
            checks["panel_hidden_at_start"] = not ws_visible(panel)
            at_panel = window_from_point(px + pw // 2, py + ph // 2)
            checks["window_from_point_at_panel"] = at_panel
            checks["panel_not_blocking_clicks"] = at_panel != panel
            time.sleep(2.0)
            checks["panel_ws_visible_after_wait"] = ws_visible(panel)
            checks["stays_hidden"] = not ws_visible(panel)

        ball = find_ball(win32)
        checks["idle_ball_visible"] = bool(ball)
        if ball:
            bx, by, bw, bh = win32.get_window_rect(ball)
            click(win32, bx + bw // 2, by + bh // 2)
            snap = wait_for(lambda s: s.get("state") == "idle_open", 8)
            checks["state_after_click"] = snap.get("state")
            shown = win32.find_window(PANEL_TITLE, timeout_s=5.0)
            checks["panel_shown_ws_visible"] = bool(shown) and ws_visible(shown)
            ctl("to-ball")
            wait_for(lambda s: s.get("state") == "idle", 8)
            time.sleep(0.6)
            checks["panel_hidden_again"] = bool(panel) and not ws_visible(panel)
    finally:
        checks["exit_code"] = stop(proc)

    ok = (
        checks.get("panel_hwnd_found") is True
        and checks.get("panel_hidden_at_start") is True
        and checks.get("panel_not_blocking_clicks") is True
        and checks.get("stays_hidden") is True
        and checks.get("idle_ball_visible") is True
        and checks.get("state_after_click") == "idle_open"
        and checks.get("panel_shown_ws_visible") is True
        and checks.get("panel_hidden_again") is True
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
