"""M29 验收：环绕球双击暂停/恢复公转（单击仍是回到面板）。

用假宠物窗口（类名 MascotFakePet）把运行时带进 tracking，再 ctl to-ball 进环绕态：
1. 环绕球在动（state.json 的 ball_circle 一段时间内位移 > 3px）
2. 在球上双击 → orbit_paused=true，且状态仍是 orbital（没有顺手打开面板）
3. 暂停后球面位置冻结（0.8s 内位移 ≤ 1px），时钟仍在走
4. 再双击 → orbit_paused=false，球继续动
5. 单击 → 回到面板（state=idle_open）
6. ctl stop → 退出码 0

为了点击可靠，验收把 orbit_speed 设为 0.05（用户配置，热重载），球移动 10px/s，
state.json 里 1s 前记录的球心与真实球心相差不到 12px，命中圆半径 ~50px。
"""
import contextlib
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
)
STATE = STATE_DIR / "state.json"
RUNTIME = STATE_DIR / "runtime.json"
FAKE_CLASS = "MascotFakePet"

user32 = ctypes.windll.user32

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def read_json(path: Path) -> dict:
    with contextlib.suppress(Exception):
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def wait_for(pred, timeout=25.0) -> dict:
    t0 = time.time()
    snap = {}
    while time.time() - t0 < timeout:
        snap = read_json(STATE)
        if pred(snap):
            return snap
        time.sleep(0.05)
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


class FakePet:
    def __init__(self, x: int, y: int, w: int = 420, h: int = 320) -> None:
        self._proc = WNDPROC(lambda h, m, wp, lp: user32.DefWindowProcW(h, m, wp, lp))
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._proc
        wc.lpszClassName = FAKE_CLASS
        wc.hInstance = None
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = int(
            user32.CreateWindowExW(
                0, FAKE_CLASS, "fake-pet", 0x80000000, x, y, w, h, None, None, None, None
            )
            or 0
        )
        self._alive = True
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        msg = wintypes.MSG()
        while self._alive:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)

    def show(self) -> None:
        user32.ShowWindow(wintypes.HWND(self.hwnd), 5)

    def close(self) -> None:
        self._alive = False
        user32.DestroyWindow(wintypes.HWND(self.hwnd))


def spawn() -> subprocess.Popen:
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = FAKE_CLASS
    return subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        cwd=str(ROOT),
        env=env,
    )


def click(win32, x: int, y: int, gap: float = 0.0) -> None:
    win32.set_cursor_pos(x, y)
    time.sleep(0.12)
    win32.mouse_left(True)
    time.sleep(0.04)
    win32.mouse_left(False)
    if gap:
        time.sleep(gap)
        win32.mouse_left(True)
        time.sleep(0.04)
        win32.mouse_left(False)


def circle() -> tuple[int, int, int] | None:
    c = read_json(STATE).get("ball_circle")
    if isinstance(c, list) and len(c) == 3:
        return int(c[0]), int(c[1]), int(c[2])
    return None


def wait_move(start, threshold: float, timeout: float = 4.0) -> float:
    """轮询球心位移：state.json 每秒才写一次，固定间隔采样可能读到同一份。"""
    best = 0.0
    t0 = time.time()
    while time.time() - t0 < timeout:
        cur = circle()
        best = displacement(start, cur)
        if best > threshold:
            return round(best, 1)
        time.sleep(0.15)
    return round(best, 1)


def displacement(a, b) -> float:
    if not a or not b:
        return -1.0
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


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
    config("set", "orbit_speed", "0.05")

    checks: dict[str, object] = {}
    pet = FakePet(360, 260)
    pet.show()
    time.sleep(0.5)
    proc = spawn()
    try:
        snap = wait_for(lambda s: s.get("state") == "tracking", 30)
        checks["state_tracking"] = snap.get("state") == "tracking"
        time.sleep(1.2)
        ctl("to-ball")
        snap = wait_for(lambda s: s.get("state") == "orbital", 15)
        checks["state_orbital"] = snap.get("state") == "orbital"
        time.sleep(1.2)

        c0 = circle()
        checks["ball_circle"] = list(c0) if c0 else None
        checks["ball_visible"] = bool(c0)
        checks["moved_before"] = wait_move(c0, 3)
        checks["orbiting_before_pause"] = float(checks["moved_before"]) > 3
        c1 = circle()

        # 双击球：暂停
        if not c1:
            raise SystemExit(5)
        click(win32, c1[0], c1[1], gap=0.08)
        time.sleep(0.8)
        snap = read_json(STATE)
        checks["orbit_paused"] = snap.get("orbit_paused")
        checks["still_orbital"] = snap.get("state") == "orbital"
        p0 = circle()
        time.sleep(1.3)
        p1 = circle()
        checks["moved_while_paused"] = round(displacement(p0, p1), 1)
        checks["frozen_while_paused"] = 0 <= displacement(p0, p1) <= 1

        # 再双击：恢复
        if not p1:
            raise SystemExit(5)
        click(win32, p1[0], p1[1], gap=0.08)
        time.sleep(0.8)
        checks["orbit_resumed"] = read_json(STATE).get("orbit_paused") is False
        r0 = circle()
        checks["moved_after_resume"] = wait_move(r0, 3)
        checks["orbiting_after_resume"] = float(checks["moved_after_resume"]) > 3
        r1 = circle()

        # 单击：离开环绕态回到面板（有宠物时是 tracking，面板重新出现）
        if not r1:
            raise SystemExit(5)
        click(win32, r1[0], r1[1])
        snap = wait_for(lambda s: s.get("state") != "orbital", 8)
        checks["single_click_returns_panel"] = snap.get("state") in ("tracking", "idle_open")
    finally:
        checks["exit_code"] = stop(proc)
        config("unset", "orbit_speed")
        pet.close()

    ok = (
        checks.get("state_tracking") is True
        and checks.get("state_orbital") is True
        and checks.get("ball_visible") is True
        and checks.get("orbiting_before_pause") is True
        and checks.get("orbit_paused") is True
        and checks.get("still_orbital") is True
        and checks.get("frozen_while_paused") is True
        and checks.get("orbit_resumed") is True
        and checks.get("orbiting_after_resume") is True
        and checks.get("single_click_returns_panel") is True
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
