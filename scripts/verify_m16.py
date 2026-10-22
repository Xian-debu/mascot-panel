"""M16 验收：待机球右键菜单 + 边缘吸附 + 回到右下角。

无宠物启动（null provider）：
1. 待机球可见
2. 拖到屏幕右边缘：松手后自动贴边（x = 工作区右 - 128 - 8）
3. 右键弹出菜单（#32768 菜单窗口出现）
4. 键盘选"小球回到右下角"：位置回默认、runtime.json 的 ball_pos 被清掉
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
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return json.loads(proc.stdout)
    return {"ok": False, "raw": proc.stdout + proc.stderr}


def spawn() -> subprocess.Popen:
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    for path in (STATE, STATE_DIR / "control.json"):
        with contextlib.suppress(OSError):
            path.unlink()
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


def find_menu(win32) -> int:
    for h in win32.enum_windows():
        if win32.get_class_name(h) == "#32768" and win32.is_visible(h):
            return h
    return 0


def key(vk: int, times: int = 1, delay: float = 0.06) -> None:
    from mascot_win import win32

    menu = find_menu(win32)
    if not menu:
        return
    for _ in range(times):
        win32.post_message(menu, 0x0100, vk, 0)  # WM_KEYDOWN
        win32.post_message(menu, 0x0101, vk, 0)  # WM_KEYUP
        time.sleep(delay)


def drag(win32, x0: int, y0: int, x1: int, y1: int) -> None:
    win32.set_cursor_pos(x0, y0)
    time.sleep(0.15)
    win32.mouse_left(True)
    time.sleep(0.12)
    for step in range(1, 9):
        win32.set_cursor_pos(x0 + (x1 - x0) * step // 8, y0 + (y1 - y0) * step // 8)
        time.sleep(0.03)
    win32.mouse_left(False)
    time.sleep(1.4)


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
        checks["ball_rect"] = [bx, by, bw, bh]
        wx, wy, ww, wh = win32.work_area(bx + bw // 2, by + bh // 2)
        checks["work_area"] = [wx, wy, ww, wh]

        # 1) 拖到右边缘：应吸附成 工作区右 - 128 - 8
        target_x = wx + ww - 4 - bw // 2  # 光标停在边缘内 4px → 球被夹到边缘
        drag(win32, bx + bw // 2, by + bh // 2, target_x, by + bh // 2)
        ax, ay, aw, ah = win32.get_window_rect(ball)
        checks["ball_rect_after_edge_drag"] = [ax, ay, aw, ah]
        checks["edge_snap_x"] = ax == wx + ww - bw - 8
        time.sleep(0.6)
        saved = {}
        with contextlib.suppress(Exception):
            saved = json.loads(RUNTIME.read_text(encoding="utf-8"))
        checks["snapped_ball_pos_saved"] = saved.get("ball_pos") == [ax, ay]

        # 2) 右键弹菜单
        win32.set_cursor_pos(ax + aw // 2, ay + ah // 2)
        time.sleep(0.15)
        win32.post_message(ball, win32.WM_RBUTTONUP, 0, 0)
        menu = 0
        deadline = time.time() + 5
        while time.time() < deadline and not menu:
            time.sleep(0.1)
            menu = find_menu(win32)
        checks["context_menu_opens"] = bool(menu)

        # 3) 键盘选"小球回到右下角"（第 6 个可选项）后回车
        if menu:
            key(0x28, 6)  # VK_DOWN ×6 → 小球回到右下角
            key(0x0D)  # VK_RETURN
            time.sleep(1.2)
        rx, ry, rw, rh = win32.get_window_rect(ball)
        checks["ball_rect_after_reset"] = [rx, ry, rw, rh]
        br_x = wx + ww - bw - 24
        br_y = wy + wh - bh - 24
        checks["reset_to_bottom_right"] = abs(rx - br_x) <= 4 and abs(ry - br_y) <= 4
        time.sleep(0.6)
        with contextlib.suppress(Exception):
            saved = json.loads(RUNTIME.read_text(encoding="utf-8"))
        checks["ball_pos_cleared"] = "ball_pos" not in saved
    finally:
        ctl("stop")
        try:
            checks["exit_code"] = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            checks["exit_code"] = -1

    ok = (
        checks.get("idle_ball_visible") is True
        and checks.get("edge_snap_x") is True
        and checks.get("snapped_ball_pos_saved") is True
        and checks.get("context_menu_opens") is True
        and checks.get("reset_to_bottom_right") is True
        and checks.get("ball_pos_cleared") is True
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
