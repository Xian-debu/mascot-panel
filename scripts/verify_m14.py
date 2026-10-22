"""M14 验收：待机球像素时钟化 + 可拖动 + 位置记忆。

无宠物启动（env 覆盖 tracker 配置）→ idle 球在右下角：
1. 待机球可见，尺寸 128（像素时钟球）
2. 用真实鼠标注入把球拖到左上 160/120 像素：球真的移动了、状态仍是 idle（拖动不触发点击）
3. runtime.json 记下 ball_pos
4. 不移动的"点一下"仍然打开面板（拖动阈值没把点击吃掉）
5. 杀掉重启后球回到上次拖到的位置（位置持久化）
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
        checks["ball_is_clock_size"] = bw == bh == 128

        # 拖动：真实鼠标事件
        cx, cy = bx + bw // 2, by + bh // 2
        win32.set_cursor_pos(cx, cy)
        time.sleep(0.15)
        win32.mouse_left(True)
        time.sleep(0.12)
        for step in range(1, 9):
            win32.set_cursor_pos(cx - 160 * step // 8, cy - 120 * step // 8)
            time.sleep(0.03)
        win32.mouse_left(False)
        time.sleep(1.6)  # 等一秒一次的待机重渲染，确认没弹回角落

        nx, ny, nw, nh = win32.get_window_rect(ball)
        checks["ball_rect_after_drag"] = [nx, ny, nw, nh]
        checks["drag_moved_ball"] = abs(nx - (bx - 160)) <= 12 and abs(ny - (by - 120)) <= 12
        checks["state_still_idle"] = read_state().get("state") == "idle"
        time.sleep(0.6)
        saved = {}
        with contextlib.suppress(Exception):
            saved = json.loads(RUNTIME.read_text(encoding="utf-8"))
        checks["ball_pos_saved"] = saved.get("ball_pos") == [nx, ny]

        # 不移动的点击仍然开面板
        win32.set_cursor_pos(nx + nw // 2, ny + nh // 2)
        time.sleep(0.15)
        win32.mouse_left(True)
        time.sleep(0.05)
        win32.mouse_left(False)
        snap = wait_for(lambda s: s.get("state") == "idle_open", 10)
        checks["click_after_drag_opens_panel"] = snap.get("state")
        ctl("to-ball")
        wait_for(lambda s: s.get("state") == "idle", 10)
    finally:
        ctl("stop")
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)

    # 重启：位置应该被记住
    proc2 = spawn()
    try:
        wait_for(lambda s: s.get("state") == "idle", 30)
        time.sleep(1.5)
        ball2 = find_ball(win32)
        checks["restart_ball_visible"] = bool(ball2)
        if ball2:
            rx, ry, rw, rh = win32.get_window_rect(ball2)
            checks["ball_rect_after_restart"] = [rx, ry, rw, rh]
            recorded = None
            with contextlib.suppress(Exception):
                recorded = json.loads(RUNTIME.read_text(encoding="utf-8")).get("ball_pos")
            checks["position_restored"] = isinstance(recorded, list) and abs(
                rx - recorded[0]
            ) <= 8 and abs(ry - recorded[1]) <= 8
    finally:
        ctl("stop")
        try:
            checks["exit_code"] = proc2.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc2.kill()
            checks["exit_code"] = -1

    ok = (
        checks.get("idle_ball_visible") is True
        and checks.get("ball_is_clock_size") is True
        and checks.get("drag_moved_ball") is True
        and checks.get("state_still_idle") is True
        and checks.get("ball_pos_saved") is True
        and checks.get("click_after_drag_opens_panel") == "idle_open"
        and checks.get("restart_ball_visible") is True
        and checks.get("position_restored") is True
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
