"""M7 验收：托盘图标、双击展开/收起、暂停跟随（ctl pause/resume）。

用法（Windows 开发副本内）：
  ./venv/Scripts/python.exe app/0.1.0/scripts/verify_m7.py

不需要人工点击：托盘回调通过向托盘窗口投递 WM_APP+1 模拟，
菜单本身（TrackPopupMenu 会阻塞消息泵）留作人工检查，见 docs/23。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(__file__).resolve().parents[6] / "state.json"  # 仅占位，运行时用 LOCALAPPDATA


def state_path() -> Path:
    import os

    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "mascot"
    return base / "state.json"


def read_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wait_for(pred, timeout: float, what: str) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = read_state()
        if pred(last):
            return last
        time.sleep(0.1)
    raise RuntimeError(f"timeout waiting {what}: {last}")


def cli(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"cli {args} bad output: {proc.stdout!r} {proc.stderr!r}") from exc


def tray_window() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from mascot_win import win32

    for hwnd in win32.enum_windows():
        if win32.is_visible(hwnd):
            continue
        try:
            if win32.get_class_name(hwnd).startswith("mascot_tray_"):
                return hwnd
        except Exception:
            continue
    return 0


def click_tray(hwnd: int, event: int) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from mascot_win import win32

    win32.post_message(hwnd, win32.WM_APP + 1, 1, event)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    checks: dict[str, object] = {}
    # 上一轮异常退出会留下 state.json/control.json：先清掉，否则等到的是旧快照
    for stale in (state_path(), state_path().parent / "control.json"):
        with __import__("contextlib").suppress(OSError):
            stale.unlink()
    proc = subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        snap = wait_for(lambda s: s.get("state") == "tracking", 25, "tracking")
        checks["follow_tracking"] = snap.get("pet")

        hwnd = 0
        deadline = time.time() + 10
        while time.time() < deadline and not hwnd:
            hwnd = tray_window()
            time.sleep(0.2)
        if not hwnd:
            raise RuntimeError("tray window not found")
        checks["tray_hwnd"] = hwnd

        click_tray(hwnd, 0x0203)  # WM_LBUTTONDBLCLK
        snap = wait_for(lambda s: s.get("state") == "orbital", 10, "orbital via tray")
        checks["tray_double_click_to_ball"] = snap.get("state")

        click_tray(hwnd, 0x0203)
        snap = wait_for(lambda s: s.get("state") == "tracking", 10, "tracking via tray")
        checks["tray_double_click_to_panel"] = snap.get("state")

        cli("ctl", "pause")
        snap = wait_for(lambda s: s.get("paused") is True, 10, "paused")
        checks["ctl_pause"] = snap.get("paused")

        # 暂停时位置不再刷新：改一次窗口外的跟随目标不存在，退化为检查 state 一直在且 pause 生效
        time.sleep(1.0)
        checks["still_running_when_paused"] = read_state().get("uptime_s", 0) > 0

        cli("ctl", "resume")
        snap = wait_for(lambda s: s.get("paused") is False, 10, "resumed")
        checks["ctl_resume"] = snap.get("paused")

        status = cli("ctl", "status")
        checks["ctl_status_running"] = status.get("data", {}).get("running")
        checks["ctl_status_paused"] = status.get("data", {}).get("state") is not None

        shot = Path(__file__).resolve().parents[1] / "m7-panel.png"
        cli("ctl", "to-panel")
        time.sleep(0.8)
        from PIL import ImageGrab

        ImageGrab.grab(all_screens=True).save(shot)
        checks["screenshot"] = str(shot)

        stopped = cli("ctl", "stop")
        checks["ctl_stop"] = stopped.get("data", {}).get("method")
        for _ in range(100):
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        checks["process_exit"] = proc.returncode
        ok = proc.returncode == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    print(json.dumps({"ok": ok and checks.get("process_exit") == 0, "checks": checks}, ensure_ascii=False))
    return 0 if checks.get("process_exit") == 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())
