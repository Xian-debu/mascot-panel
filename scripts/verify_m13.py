"""M13 验收：宠物不在时的待机形态（右下角常驻小球 + 独立面板）。

用一个"永远找不到宠物"的配置启动（env 覆盖进程名/窗口类），于是状态停在 idle：
- 待机小球可见（右下角），state.json = idle
- 点球（真实 WM_LBUTTONUP）→ idle_open，面板出现且贴在屏幕右下角
- ctl to-ball → 回到 idle，面板隐藏、球仍在
- ctl to-panel → 再开面板（ctl 与点击等价）
- ctl stop → 退出码 0
"""
import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot" / "state.json"


def read_state() -> dict:
    for _ in range(40):
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
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", "ctl", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"ok": False, "raw": proc.stdout + proc.stderr}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from mascot_win import win32

    # 验收脚本自己也要声明 DPI 感知，否则 work_area/get_window_rect 拿到的是
    # 逻辑坐标（1707x1067），和面板的物理尺寸（488x634）对不上，判据必然失败。
    win32.enable_dpi_awareness()

    with contextlib.suppress(OSError):
        STATE.unlink()
    with contextlib.suppress(OSError):
        (STATE.parent / "control.json").unlink()

    env = dict(os.environ)
    # 让 tracker 永远匹配不到宠物：进程名与窗口类都改成不存在的值
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    proc = subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        cwd=str(ROOT),
        env=env,
    )
    checks: dict[str, object] = {}
    try:
        snap = wait_for(lambda s: s.get("state") == "idle")
        checks["idle_without_pet"] = snap.get("state")
        checks["pet_is_none"] = snap.get("pet") is None

        time.sleep(1.5)  # 等第一帧待机小球渲染
        balls = [
            h
            for h in win32.enum_windows()
            if win32.get_class_name(h).startswith("mascot_layered_") and win32.is_visible(h)
        ]
        checks["idle_ball_visible"] = len(balls) > 0
        ball = balls[0] if balls else 0
        if ball:
            bx, by, bw, bh = win32.get_window_rect(ball)
            checks["ball_rect"] = [bx, by, bw, bh]

        # 真实点击：走 WM_LBUTTONUP 的真实 wndproc 分支
        if ball:
            win32.post_message(ball, win32.WM_LBUTTONDOWN, 1, 0)
            win32.post_message(ball, win32.WM_LBUTTONUP, 0, 0)
        snap = wait_for(lambda s: s.get("state") == "idle_open", 10)
        checks["click_ball_opens_panel"] = snap.get("state")

        panel = win32.find_window("mascot-panel", timeout_s=3.0)
        checks["panel_visible"] = bool(panel) and win32.is_visible(panel)
        if panel:
            px, py, pw, ph = win32.get_window_rect(panel)
            wx, wy, ww, wh = win32.work_area(px + pw // 2, py + ph // 2)
            checks["panel_rect"] = [px, py, pw, ph]
            checks["work_area"] = [wx, wy, ww, wh]
            checks["panel_deltas"] = [abs((px + pw) - (wx + ww)), abs((py + ph) - (wy + wh))]
            checks["panel_at_bottom_right"] = (
                abs((px + pw) - (wx + ww)) <= 60 and abs((py + ph) - (wy + wh)) <= 60
            )

        # ctl 收球 → 回到 idle，球回来、面板消失
        ctl("to-ball")
        snap = wait_for(lambda s: s.get("state") == "idle", 10)
        checks["ctl_to_ball_returns_idle"] = snap.get("state")
        time.sleep(0.6)
        checks["panel_hidden_after_to_ball"] = not (
            panel and win32.is_visible(win32.find_window("mascot-panel", timeout_s=0.5))
        )

        ctl("to-panel")
        snap = wait_for(lambda s: s.get("state") == "idle_open", 10)
        checks["ctl_to_panel_reopens"] = snap.get("state")
    finally:
        ctl("stop")
        try:
            checks["exit_code"] = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            checks["exit_code"] = -1

    must = [
        "idle_without_pet",
        "pet_is_none",
        "idle_ball_visible",
        "click_ball_opens_panel",
        "panel_visible",
        "panel_at_bottom_right",
        "ctl_to_ball_returns_idle",
        "panel_hidden_after_to_ball",
        "ctl_to_panel_reopens",
    ]
    ok = (
        checks.get("idle_without_pet") == "idle"
        and checks.get("pet_is_none") is True
        and checks.get("idle_ball_visible") is True
        and checks.get("click_ball_opens_panel") == "idle_open"
        and checks.get("panel_visible") is True
        and checks.get("panel_at_bottom_right") is True
        and checks.get("ctl_to_ball_returns_idle") == "idle"
        and checks.get("panel_hidden_after_to_ball") is True
        and checks.get("ctl_to_panel_reopens") == "idle_open"
        and checks.get("exit_code") == 0
    )
    checks["missing"] = [name for name in must if name not in checks]
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
