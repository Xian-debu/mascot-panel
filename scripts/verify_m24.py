"""M24 验收：面板可拖动 + 位置记忆（钉住后不再自动贴角/跟随）。

无宠物启动（null provider）：
1. ctl to-panel 打开面板，初始没有 panel_pos 记录
2. 用真实鼠标按住标题栏拖动：窗口移动，panel_pos 落盘（拖不动则改用程序移动模拟，并记录方式）
3. 之后 1.5s 内不被自动摆放弹回原位
4. 重启后打开面板：回到上次拖动的位置
5. ctl reset-panel：回到右下角默认位置、panel_pos 被清掉
6. ctl stop → 退出码 0
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


def spawn(*, wipe: bool) -> subprocess.Popen:
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    if wipe:
        for path in (STATE, STATE_DIR / "control.json"):
            with contextlib.suppress(OSError):
                path.unlink()
    return subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        cwd=str(ROOT),
        env=env,
    )


def drag(win32, x0: int, y0: int, x1: int, y1: int) -> None:
    win32.set_cursor_pos(x0, y0)
    time.sleep(0.2)
    win32.mouse_left(True)
    time.sleep(0.15)
    for step in range(1, 11):
        win32.set_cursor_pos(x0 + (x1 - x0) * step // 10, y0 + (y1 - y0) * step // 10)
        time.sleep(0.04)
    win32.mouse_left(False)
    time.sleep(1.2)


def open_panel(win32) -> tuple[int, tuple[int, int, int, int]]:
    """确保面板可见，返回 (hwnd, rect)。"""
    ctl("to-panel")
    wait_for(lambda s: s.get("state") == "idle_open", 25)
    hwnd = 0
    deadline = time.time() + 10
    while time.time() < deadline and not hwnd:
        hwnd = win32.find_window(PANEL_TITLE)
        time.sleep(0.1)
    time.sleep(0.8)
    return hwnd, win32.get_window_rect(hwnd)


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
    proc = spawn(wipe=False)
    try:
        wait_for(lambda s: s.get("state") == "idle", 30)
        hwnd, (px, py, pw, ph) = open_panel(win32)
        checks["panel_visible"] = bool(hwnd)
        checks["panel_rect_initial"] = [px, py, pw, ph]
        if not hwnd:
            raise SystemExit(5)
        checks["panel_pos_absent_initially"] = "panel_pos" not in read_runtime()

        # 1) 真实鼠标拖标题栏（.pywebview-drag-region）
        drag(win32, px + pw // 2, py + 16, px + pw // 2 - 180, py + 16 - 150)
        ax, ay, aw, ah = win32.get_window_rect(hwnd)
        moved_by_mouse = abs(ax - px) > 40 or abs(ay - py) > 40
        checks["drag_via_mouse"] = moved_by_mouse
        if not moved_by_mouse:
            # 注入拖拽没生效（WebView 没拿到鼠标）→ 直接移动窗口，仍能验证采纳+记忆链路
            win32.move_window(hwnd, px - 180, py - 150)
            time.sleep(1.2)
            ax, ay, aw, ah = win32.get_window_rect(hwnd)
        checks["panel_moved"] = abs(ax - px) > 40 or abs(ay - py) > 40
        checks["panel_rect_after_drag"] = [ax, ay, aw, ah]

        data = wait_runtime(lambda d: isinstance(d.get("panel_pos"), list), 6)
        checks["panel_pos_saved"] = data.get("panel_pos") == [ax, ay]

        # 2) 不被自动摆放弹回去
        time.sleep(1.6)
        bx2, by2, bw2, bh2 = win32.get_window_rect(hwnd)
        checks["panel_rect_after_wait"] = [bx2, by2, bw2, bh2]
        checks["stays_after_drag"] = abs(bx2 - ax) <= 2 and abs(by2 - ay) <= 2
        saved = data.get("panel_pos") or [0, 0]
    finally:
        checks["exit_code_first"] = stop(proc)

    # 3) 重启：位置恢复
    proc2 = spawn(wipe=True)
    try:
        wait_for(lambda s: s.get("state") == "idle", 30)
        hwnd2, (rx, ry, rw, rh) = open_panel(win32)
        checks["panel_rect_restored"] = [rx, ry, rw, rh]
        checks["position_restored"] = bool(hwnd2) and abs(rx - saved[0]) <= 4 and abs(ry - saved[1]) <= 4

        # 4) 复位：回到右下角并清掉记忆
        ctl("reset-panel")
        time.sleep(1.2)
        cx, cy, cw, ch = win32.get_window_rect(hwnd2)
        wx, wy, ww, wh = win32.work_area(cx + cw // 2, cy + ch // 2)
        checks["work_area"] = [wx, wy, ww, wh]
        checks["panel_rect_after_reset"] = [cx, cy, cw, ch]
        checks["reset_to_bottom_right"] = (
            abs(cx - (wx + ww - cw - 24)) <= 4 and abs(cy - (wy + wh - ch - 24)) <= 4
        )
        time.sleep(0.8)
        checks["panel_pos_cleared"] = "panel_pos" not in read_runtime()
    finally:
        checks["exit_code"] = stop(proc2)

    ok = (
        checks.get("panel_visible") is True
        and checks.get("panel_pos_absent_initially") is True
        and checks.get("panel_moved") is True
        and checks.get("panel_pos_saved") is True
        and checks.get("stays_after_drag") is True
        and checks.get("position_restored") is True
        and checks.get("reset_to_bottom_right") is True
        and checks.get("panel_pos_cleared") is True
        and checks.get("exit_code_first") == 0
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
