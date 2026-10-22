#!/usr/bin/env python3
"""M4 验收：真跑一个实例，走面板/ctl 的聊天链路，逐项断言。

前置：provider 后端可用（WSL 侧 scripts/dev-chat-backend.py，或真后端）。
用法（Windows venv）：
    python app/0.1.0/scripts/verify_m4.py --provider-url http://127.0.0.1:8891
退出码：0 全部通过 / 5 有检查失败。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time


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


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider-url", default="http://127.0.0.1:8891")
    ap.add_argument("--run-seconds", type=float, default=25.0)
    args = ap.parse_args()

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
            "--provider",
            "wsl",
            "--provider-url",
            args.provider_url,
            "--duration",
            str(args.run_seconds),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )

    try:
        data = wait_for(lambda d: d.get("running") and d.get("messages"), 20.0)
        check("panel_follows_pet", bool(data and data.get("pet")), data.get("pet") if data else None)
        check(
            "history_loaded",
            bool(data and len(data.get("messages", [])) >= 1),
            len(data.get("messages", [])) if data else 0,
        )

        marker = f"验收消息-{int(time.time())}"
        code, payload = cli("ctl", "send", "--text", marker)
        check("ctl_send_accepted", code == 0, payload.get("data") if code == 0 else payload)

        data = wait_for(
            lambda d: any(
                m.get("role") == "user" and m.get("text") == marker for m in d.get("messages", [])
            )
            and any(m.get("role") == "assistant" and marker[:12] in m.get("text", "") for m in d.get("messages", [])),
            10.0,
        )
        check("user_message_stored", bool(data), marker if data else "timeout")
        check("assistant_reply_received", bool(data), "见 messages")

        code, payload = cli("ctl", "status")
        status = payload.get("data", {})
        check("not_sending_after_reply", status.get("sending") is False, status.get("sending"))
        check("provider_not_degraded", status.get("degraded") is False, status.get("state"))

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

    failed = [name for name, ok, _ in results if not ok]
    print("RESULT:", "PASS" if not failed else f"FAIL {failed}", flush=True)
    return 0 if not failed else 5


if __name__ == "__main__":
    raise SystemExit(main())
