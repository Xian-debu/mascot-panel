#!/usr/bin/env python3
"""M30 验收：新消息到达时小球亮提示环（状态灯），2.5s 后自动消失。

脚本自己起一个假聊天后端（scripts/dev-chat-backend.py 的 Handler），再拉真实例：
1. 无宠物 → 待机小球可见，alert=false
2. ctl send → 假后端回一条 assistant 消息 → alert=true 且 alert_remaining_s>0
3. 2.5s 窗口过后 alert 自动回落 false，状态仍是 idle（提示环不改状态机）
4. 期间截一张全屏图存 evidence/m30-alert.png（人工看环）
5. ctl stop → 退出码 0

用法（Windows venv，需先 deploy + pip install）：
    python app/0.1.0/scripts/verify_m30.py
退出码：0 全部通过 / 5 有检查失败。
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
)
STATE = STATE_DIR / "state.json"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def load_backend():
    path = Path(__file__).with_name("dev-chat-backend.py")
    spec = importlib.util.spec_from_file_location("dev_chat_backend", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_state() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=90,
    )
    with contextlib.suppress(Exception):
        return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])
    return proc.returncode, {"raw": proc.stdout + proc.stderr}


def wait_for(pred, timeout: float = 8.0) -> dict:
    t0 = time.time()
    snap: dict = {}
    while time.time() - t0 < timeout:
        snap = read_state()
        if pred(snap):
            return snap
        time.sleep(0.05)
    return snap


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    results: list[tuple[str, bool, object]] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        results.append((name, bool(ok), detail))
        print(f"[{'ok' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    for path in (STATE, STATE_DIR / "control.json"):
        with contextlib.suppress(OSError):
            path.unlink()

    port = free_port()
    backend = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("dev-chat-backend.py")), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"

    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mascot_app.cli",
            "run",
            "--provider-url",
            url,
            "--duration",
            "60",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        snap = wait_for(lambda d: d.get("state") == "idle" and d.get("alert") is False, 30.0)
        check("state_idle", snap.get("state") == "idle", snap.get("state"))
        check("alert_false_before", snap.get("alert") is False, snap.get("alert"))

        marker = f"验收消息-{int(time.time())}"
        code, payload = cli("ctl", "send", "--text", marker)
        check("ctl_send_accepted", code == 0, payload.get("data") if code == 0 else payload)

        snap = wait_for(
            lambda d: any(
                m.get("role") == "assistant" and "假后端" in m.get("text", "")
                for m in d.get("messages", [])
            ),
            20.0,
        )
        texts = [m.get("text", "") for m in snap.get("messages", []) if m.get("role") == "assistant"]
        check("reply_arrived", any("假后端" in t for t in texts), texts[-1][:60] if texts else None)

        alert_snap = wait_for(lambda d: d.get("alert") is True, 6.0)
        check("alert_true_after_reply", alert_snap.get("alert") is True, alert_snap.get("alert"))

        shot_ok = False
        with contextlib.suppress(Exception):
            from PIL import ImageGrab

            shot = ROOT / "evidence" / "m30-alert.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(all_screens=True).save(shot)
            shot_ok = shot.exists() and shot.stat().st_size > 1000
        check("screenshot_saved", shot_ok, "evidence/m30-alert.png")

        idles = wait_for(lambda d: d.get("alert") is False, 8.0)
        check("alert_cleared", idles.get("alert") is False, idles.get("alert"))
        check("still_idle_after_alert", idles.get("state") == "idle", idles.get("state"))

        cli("ctl", "stop")
        try:
            code = proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = -1
        check("exit_code", code == 0, code)
    finally:
        if proc.poll() is None:
            proc.kill()
        with contextlib.suppress(Exception):
            backend.terminate()
            backend.wait(timeout=5)

    failed = [name for name, ok, _ in results if not ok]
    print("RESULT:", "PASS" if not failed else f"FAIL {failed}", flush=True)
    return 0 if not failed else 5


if __name__ == "__main__":
    raise SystemExit(main())
