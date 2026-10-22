"""M25 验收：待机球单击开面板 / 双击回右下角（350ms 时间窗区分）。

无宠物启动（null provider）：
1. 待机球出现在右下角
2. 真实鼠标把球拖到屏幕中间，位置被记住
3. 双击球：球回到右下角、ball_pos 清掉、面板没有打开（状态仍是 idle）
4. 之后单击球：面板照常打开（双击没有把点击吞掉）
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
RUNTIME = STATE_DIR / "runtime.json"
PANEL_TITLE = "mascot-panel"


def read_state() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def read_runtime() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(RUNTIME.read_text(encoding="utf-8"))
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


def wait_runtime(pred, timeout=8.0) -> dict:
    t0 = time.time()
    data = {}
    while time.time() - t0 < timeout:
        data = read_runtime()
        if pred(data):
            return data
        time.sleep(0.1)
    return data


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


def find_ball(win32) -> int:
    for h in win32.enum_windows():
        if win32.get_class_name(h).startswith("mascot_layered_") and win32.is_visible(h):
            return h
    return 0


def drag(win32, x0: int, y0: int, x1: int, y1: int) -> None:
    win32.set_cursor_pos(x0, y0)
    time.sleep(0.2)
    win32.mouse_left(True)
    time.sleep(0.15)
    for step in range(1, 11):
        win32.set_cursor_pos(x0 + (x1 - x0) * step // 10, y0 + (y1 - y0) * step // 10)
        time.sleep(0.04)
    win32.mouse_left(False)
    time.sleep(1.0)


def click(win32, x: int, y: int) -> None:
    win32.set_cursor_pos(x, y)
    time.sleep(0.15)
    win32.mouse_left(True)
    time.sleep(0.05)
    win32.mouse_left(False)


def double_click(win32, x: int, y: int) -> None:
    """两次点击间隔 80ms，落在 350ms 的双击窗口内。"""
    click(win32, x, y)
    time.sleep(0.08)
    click(win32, x, y)


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
    for path in (STATE, STATE_DIR / "control.json", RUNTIME):
        with contextlib.suppress(OSError):
            path.unlink()

    checks: dict[str, object] = {}
    proc = spawn()
    try:
        wait_for(lambda s: s.get("state") == "idle", 30)
        time.sleep(1.5)
        ball = find_ball(win32)
        checks["idle_ball_visible"] = bool(ball)
        if not ball:
            raise SystemExit(5)
        bx, by, bw, bh = win32.get_window_rect(ball)
        checks["ball_rect_initial"] = [bx, by, bw, bh]
        wx, wy, ww, wh = win32.work_area(bx + bw // 2, by + bh // 2)
        checks["work_area"] = [wx, wy, ww, wh]
        checks["ball_starts_in_corner"] = (
            abs(bx - (wx + ww - bw - 24)) <= 4 and abs(by - (wy + wh - bh - 24)) <= 4
        )

        # 1) 先拖到屏幕中间，位置被记住（后面双击要能把它送回角落）
        drag(win32, bx + bw // 2, by + bh // 2, wx + ww // 3, wy + wh // 3)
        dx, dy, dw, dh = win32.get_window_rect(ball)
        checks["ball_rect_after_drag"] = [dx, dy, dw, dh]
        checks["dragged_away_from_corner"] = (
            abs(dx - bx) > 40 or abs(dy - by) > 40
        )
        checks["drag_pos_saved"] = wait_runtime(
            lambda d: isinstance(d.get("ball_pos"), list), 6
        ).get("ball_pos") == [dx, dy]

        # 2) 双击：回右下角、清掉记忆、面板不打开
        double_click(win32, dx + dw // 2, dy + dh // 2)
        time.sleep(1.2)
        ex, ey, ew, eh = win32.get_window_rect(ball)
        checks["ball_rect_after_double_click"] = [ex, ey, ew, eh]
        checks["double_click_resets_to_corner"] = (
            abs(ex - (wx + ww - ew - 24)) <= 4 and abs(ey - (wy + wh - eh - 24)) <= 4
        )
        checks["ball_pos_cleared"] = "ball_pos" not in read_runtime()
        state_after_double = wait_for(lambda s: s.get("state") != "idle", 1.2)
        checks["panel_not_opened"] = state_after_double.get("state") == "idle"

        # 3) 双击之后单击：面板照常打开（挂起点击已被双击清掉）
        click(win32, ex + ew // 2, ey + eh // 2)
        snap = wait_for(lambda s: s.get("state") == "idle_open", 6)
        checks["single_click_opens_panel"] = snap.get("state") == "idle_open"
        shown_panel = win32.find_window(PANEL_TITLE)
        px, py, pw2, ph2 = win32.get_window_rect(shown_panel) if shown_panel else (0, 0, 0, 0)
        checks["panel_rect_after_open"] = [px, py, pw2, ph2]
        checks["panel_on_screen"] = bool(shown_panel) and 0 <= px < wx + ww and 0 <= py < wy + wh
    finally:
        checks["exit_code"] = stop(proc)

    ok = (
        checks.get("idle_ball_visible") is True
        and checks.get("ball_starts_in_corner") is True
        and checks.get("dragged_away_from_corner") is True
        and checks.get("drag_pos_saved") is True
        and checks.get("double_click_resets_to_corner") is True
        and checks.get("ball_pos_cleared") is True
        and checks.get("panel_not_opened") is True
        and checks.get("single_click_opens_panel") is True
        and checks.get("panel_on_screen") is True
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
