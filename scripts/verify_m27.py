"""M27 验收：跟随态拖出来的面板记「相对宠物的偏移」，宠物移动时面板跟着走。

用一个自建假宠物窗口（类名 MascotFakePet）代替 TX-Pet：
1. 假宠物出现 → state=tracking、面板出现在默认跟随位置
2. 真实鼠标拖面板标题栏 → runtime.json 同时落 panel_pos（绝对）与 panel_offset（相对宠物）
3. 把假宠物移动 +180/+120 → 面板跟着移动，偏移保持不变
4. ctl reset-panel → 两个键都清掉，面板回到默认跟随位置
5. ctl stop → 退出码 0
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
PANEL_TITLE = "mascot-panel"
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


def wait_for(pred, timeout=25.0, src=None) -> dict:
    path = src or STATE
    t0 = time.time()
    snap = {}
    while time.time() - t0 < timeout:
        snap = read_json(path)
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


class FakePet:
    """一个可见的无边框窗口，类名 MascotFakePet，供 PetTracker 按类名发现。"""

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
                0,
                FAKE_CLASS,
                "fake-pet",
                0x80000000,  # WS_POPUP
                x,
                y,
                w,
                h,
                None,
                None,
                None,
                None,
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
        user32.ShowWindow(wintypes.HWND(self.hwnd), 5)  # SW_SHOW

    def move(self, x: int, y: int) -> None:
        user32.SetWindowPos(wintypes.HWND(self.hwnd), None, x, y, 0, 0, 0x0001 | 0x0010)

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


def drag(win32, x0: int, y0: int, x1: int, y1: int) -> None:
    win32.set_cursor_pos(x0, y0)
    time.sleep(0.2)
    win32.mouse_left(True)
    time.sleep(0.15)
    for step in range(1, 13):
        win32.set_cursor_pos(x0 + (x1 - x0) * step // 12, y0 + (y1 - y0) * step // 12)
        time.sleep(0.04)
    win32.mouse_left(False)
    time.sleep(1.2)


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
    pet = FakePet(320, 240)
    pet.show()
    time.sleep(0.5)
    proc = spawn()
    try:
        snap = wait_for(lambda s: s.get("state") == "tracking", 30)
        checks["state_tracking"] = snap.get("state") == "tracking"
        time.sleep(1.5)
        panel = win32.find_window(PANEL_TITLE, timeout_s=10.0)
        checks["panel_found"] = bool(panel)
        if not panel:
            raise SystemExit(5)
        px, py, pw, ph = win32.get_window_rect(panel)
        checks["panel_rect_initial"] = [px, py, pw, ph]
        checks["panel_near_pet_initially"] = abs(px - 320) < 500 and abs(py - 240) < 500

        # 拖面板标题栏（避开左右两侧的按钮）
        drag(win32, px + pw // 2, py + 22, px + pw // 2 - 160, py + 22 + 140)
        nx, ny, nw, nh = win32.get_window_rect(panel)
        checks["panel_rect_after_drag"] = [nx, ny, nw, nh]
        checks["panel_moved"] = abs(nx - px) > 40 or abs(ny - py) > 40
        rt = wait_for(lambda d: isinstance(d.get("panel_offset"), list), 6, src=RUNTIME)
        checks["panel_offset_saved"] = rt.get("panel_offset")
        checks["panel_pos_saved"] = rt.get("panel_pos")

        # 宠物移动 +180/+120：面板应保持同一偏移跟着走
        pet.move(320 + 180, 240 + 120)
        time.sleep(2.0)
        fx, fy, fw, fh = win32.get_window_rect(panel)
        checks["panel_rect_after_pet_move"] = [fx, fy, fw, fh]
        off = checks.get("panel_offset_saved")
        checks["panel_followed_pet"] = (
            isinstance(off, list)
            and len(off) == 2
            and abs(fx - (320 + 180 + int(off[0]))) <= 6
            and abs(fy - (240 + 120 + int(off[1]))) <= 6
        )

        # 复位：两个键都清掉，回默认跟随位置
        ctl("reset-panel")
        time.sleep(1.5)
        rt2 = read_json(RUNTIME)
        checks["panel_offset_cleared"] = "panel_offset" not in rt2
        checks["panel_pos_cleared"] = "panel_pos" not in rt2
        rx, ry, rw, rh = win32.get_window_rect(panel)
        checks["panel_rect_after_reset"] = [rx, ry, rw, rh]
        checks["reset_back_near_pet"] = abs(rx - (320 + 180)) < 600 and abs(ry - (240 + 120)) < 600
    finally:
        checks["exit_code"] = stop(proc)
        pet.close()

    ok = (
        checks.get("state_tracking") is True
        and checks.get("panel_found") is True
        and checks.get("panel_near_pet_initially") is True
        and checks.get("panel_moved") is True
        and isinstance(checks.get("panel_offset_saved"), list)
        and checks.get("panel_followed_pet") is True
        and checks.get("panel_offset_cleared") is True
        and checks.get("panel_pos_cleared") is True
        and checks.get("reset_back_near_pet") is True
        and checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
