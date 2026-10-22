"""冷启动测量：读运行中实例写出的 boot 里程碑（毫秒，相对进程启动）。

用法（Windows 开发副本或安装目录）：
  ./venv/Scripts/python.exe app/0.1.0/scripts/measure_start.py --exe <path-to-mascot.exe> --runs 3

里程碑含义见 src/mascot_app/boot.py：cli_main / worker_start / ball_ready / tray_ready /
pet_found / state_tracking / panel_hwnd / webview_started。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path


def state_path() -> Path:
    import os

    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "mascot"
    return base / "state.json"


def read_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def one_run(exe: Path, timeout: float) -> dict:
    for stale in (state_path(), state_path().parent / "control.json"):
        with contextlib.suppress(OSError):
            stale.unlink()

    t0 = time.perf_counter()
    proc = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    boot: dict = {}
    try:
        deadline = t0 + timeout
        while time.perf_counter() < deadline:
            snap = read_state()
            boot = snap.get("boot") or {}
            if "panel_hwnd" in boot and "state_tracking" in boot:
                boot = dict(boot)
                boot["panel_visible_spawn_ms"] = round((time.perf_counter() - t0) * 1000)
                break
            time.sleep(0.02)
    finally:
        with contextlib.suppress(Exception):
            subprocess.run([str(exe), "ctl", "stop"], capture_output=True, text=True, timeout=20)
        for _ in range(100):
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        if proc.poll() is None:
            proc.kill()
    boot["wall_total_ms"] = round((time.perf_counter() - t0) * 1000)
    return boot


def main() -> int:
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(Path(sys.executable).parent / "mascot.exe"))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()
    exe = Path(args.exe)
    if not exe.exists():
        print(json.dumps({"ok": False, "error": f"exe not found: {exe}"}, ensure_ascii=False))
        return 2
    runs = [one_run(exe, args.timeout) for _ in range(args.runs)]
    keys = ("cli_main", "ball_ready", "tray_ready", "pet_found", "state_tracking", "panel_hwnd")
    avg = {}
    for k in keys:
        values = [r.get(k) for r in runs if r.get(k) is not None]
        avg[k] = round(sum(values) / len(values)) if values else None
    print(json.dumps({"ok": True, "exe": str(exe), "runs": runs, "avg": avg}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
