#!/usr/bin/env python3
"""M10 验收：默认 provider(auto) 自动认领旧后端契约，走通历史 + 发送。

脚本自己起一个假 legacy 后端（scripts/dev-legacy-backend.py），再拉真实例，
然后只用 ctl/state.json 断言：

  1. 起实例（provider 用默认 auto）→ 跟随宠物、状态 tracking
  2. 历史来自 /api/pet/news（两条种子消息）
  3. ctl send → 后端 SSE 分片被拼成一条 assistant 回复
  4. 回复内容含「假旧后端」、发送态复位、未降级

用法（Windows venv，需先 deploy + pip install）：
    python app/0.1.0/scripts/verify_m10.py
退出码：0 全部通过 / 5 有检查失败。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path


def load_backend():
    path = Path(__file__).with_name("dev-legacy-backend.py")
    spec = importlib.util.spec_from_file_location("dev_legacy_backend", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        payload = {"raw": proc.stdout, "stderr": proc.stderr}
    return proc.returncode, payload


def state_data() -> dict:
    code, payload = cli("ctl", "status")
    return payload.get("data", {}) if code == 0 else {}


def wait_for(predicate, timeout_s: float, interval_s: float = 0.3) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = state_data()
        if predicate(data):
            return data
        time.sleep(interval_s)
    return None


def clear_stale_state() -> None:
    """上一轮残留的 state.json/control.json 会让断言读到旧快照。"""
    base = Path.home() / "AppData" / "Local" / "mascot"
    for name in ("state.json", "control.json"):
        target = base / name
        if target.exists():
            target.unlink()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-seconds", type=float, default=30.0)
    args = ap.parse_args()

    backend = load_backend()
    server, url = backend.serve_in_thread(0)
    print(f"fake legacy backend: {url}", flush=True)
    clear_stale_state()

    results: list[tuple[str, bool, object]] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        results.append((name, ok, detail))
        print(f"[{'ok' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mascot_app.cli",
            "run",
            "--provider-url",
            url,
            "--duration",
            str(args.run_seconds),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )

    try:
        data = wait_for(lambda d: bool(d.get("running")) and bool(d.get("messages")), 25.0)
        check("panel_follows_pet", bool(data and data.get("pet")), data.get("pet") if data else None)
        check("provider_is_auto", bool(data and data.get("provider") == "auto"), data.get("provider") if data else None)
        texts = [m.get("text", "") for m in (data or {}).get("messages", [])]
        check("legacy_history_loaded", any("在的" in t for t in texts), texts[:3])

        marker = f"验收消息-{int(time.time())}"
        code, payload = cli("ctl", "send", "--text", marker)
        check("ctl_send_accepted", code == 0, payload.get("data") if code == 0 else payload)

        data = wait_for(
            lambda d: any(
                m.get("role") == "assistant" and "假旧后端" in m.get("text", "")
                for m in d.get("messages", [])
            )
            and d.get("sending") is False,
            20.0,
        )
        reply = ""
        if data:
            replies = [m.get("text", "") for m in data.get("messages", []) if m.get("role") == "assistant"]
            if replies:
                reply = replies[-1]
        check("assistant_reply_assembled", bool(reply), reply[:60])
        check("reply_echoes_marker", marker in reply, reply[:80])
        check("not_degraded", bool(data and data.get("degraded") is False), (data or {}).get("state"))

        code, payload = cli("ctl", "stop")
        check("ctl_stop", code == 0, payload.get("data"))
        try:
            proc.wait(timeout=10)
            check("process_exited", True, proc.returncode)
        except subprocess.TimeoutExpired:
            proc.kill()
            check("process_exited", False, "still running after ctl stop")
    finally:
        if proc.poll() is None:
            proc.kill()
        server.shutdown()
        server.server_close()

    failed = [name for name, ok, _ in results if not ok]
    print("RESULT:", "PASS" if not failed else f"FAIL {failed}", flush=True)
    return 0 if not failed else 5


if __name__ == "__main__":
    raise SystemExit(main())
