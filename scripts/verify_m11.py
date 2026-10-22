#!/usr/bin/env python3
"""M11 验收：流式增量渲染 + 中途停止生成。

脚本自己起假 legacy 后端（带分片间隔），再拉真实例，断言：

  1. 起实例 → 跟随宠物、状态 tracking
  2. 发送长问题 → state.json 里能看到 streaming.active=true 且 text 在增长（增量渲染）
  3. 分片拼接完成 → 回复完整、streaming 复位、sending 复位
  4. 第二轮发送后中途 ctl cancel-send → 已收到的部分文本落成一条 assistant 消息
  5. 取消后 sending/streaming 都复位，实例未降级

用法（Windows venv，需先 deploy + pip install）：
    python app/0.1.0/scripts/verify_m11.py
退出码：0 全部通过 / 5 有检查失败。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
        timeout=120,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        payload = {"raw": proc.stdout, "stderr": proc.stderr}
    return proc.returncode, payload


def state_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "mascot" if local else Path.home() / ".mascot"


def read_state() -> dict:
    """直接读 state.json：流式断言要几十毫秒级刷新，ctl status 每次都要起进程。"""
    target = state_dir() / "state.json"
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wait_for(predicate, timeout_s: float, interval_s: float = 0.1) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = read_state()
        if predicate(data):
            return data
        time.sleep(interval_s)
    return None


def clear_stale_state() -> None:
    for name in ("state.json", "control.json"):
        target = state_dir() / name
        if target.exists():
            target.unlink()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-seconds", type=float, default=60.0)
    ap.add_argument("--chunk-delay", type=float, default=0.35)
    args = ap.parse_args()

    backend = load_backend()
    server, url = backend.serve_in_thread(0, chunk_delay=args.chunk_delay)
    print(f"fake legacy backend: {url} (chunk_delay={args.chunk_delay}s)", flush=True)
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )

    try:
        data = wait_for(lambda d: bool(d.get("pet")), 25.0, 0.2)
        check("panel_follows_pet", bool(data and data.get("pet")), (data or {}).get("pet"))

        # ---- 第一轮：完整流式 ----
        long_text = "请把今天的记录按时间顺序整理成一份摘要，并标出可疑的报错行，" * 2
        code, payload = cli("ctl", "send", "--text", long_text)
        check("ctl_send_accepted", code == 0, payload.get("data") if code == 0 else payload)

        partials: list[str] = []
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            snap = read_state()
            streaming = snap.get("streaming") or {}
            text = str(streaming.get("text") or "")
            if streaming.get("active") and text:
                partials.append(text)
            if not snap.get("sending") and any(
                m.get("role") == "assistant" and "假旧后端" in m.get("text", "")
                for m in snap.get("messages", [])
            ):
                break
            time.sleep(0.05)

        check("stream_partials_observed", len(partials) >= 2, f"{len(partials)} 次增量快照")
        check(
            "partial_grows_monotonically",
            bool(partials) and all(partials[i + 1].startswith(partials[i]) for i in range(len(partials) - 1)),
            partials[-1][:30] if partials else "",
        )

        data = wait_for(lambda d: not d.get("sending") and bool(d.get("messages")), 25.0, 0.2) or {}
        replies = [m.get("text", "") for m in data.get("messages", []) if m.get("role") == "assistant"]
        reply = replies[-1] if replies else ""
        check("reply_completed", long_text[:20] in reply and "假旧后端" in reply, reply[:40])
        check(
            "partial_is_prefix_of_reply",
            bool(partials) and reply.startswith(partials[-1]),
            (partials[-1][-20:] if partials else "") + " -> " + reply[:20],
        )
        streaming = data.get("streaming") or {}
        check("streaming_reset", streaming.get("active") is False and streaming.get("text") == "", streaming)

        # ---- 第二轮：中途停止 ----
        interrupted = long_text + "（这一轮会被打断）"
        expected_full = f"（假旧后端）收到 {len(interrupted)} 个字：{interrupted}"
        code, payload = cli("ctl", "send", "--text", interrupted)
        check("second_send_accepted", code == 0, payload.get("data") if code == 0 else payload)

        seen = wait_for(
            lambda d: bool((d.get("streaming") or {}).get("active")) and len(str((d.get("streaming") or {}).get("text") or "")) >= 6,
            25.0,
        )
        check("stream_active_before_cancel", bool(seen), (seen or {}).get("streaming"))

        code, payload = cli("ctl", "cancel-send")
        check("cancel_accepted", code == 0, payload.get("data") if code == 0 else payload)

        data = wait_for(lambda d: d.get("sending") is False and d.get("streaming", {}).get("active") is False, 15.0, 0.1) or {}
        assistant_msgs = [m for m in data.get("messages", []) if m.get("role") == "assistant"]
        last = assistant_msgs[-1] if assistant_msgs else {}
        check("partial_message_kept", bool(last.get("text")), last.get("text", "")[:40])
        kept = str(last.get("text", ""))
        check(
            "partial_short_of_full_reply",
            bool(kept) and kept != expected_full and expected_full.startswith(kept),
            f"{len(kept)}/{len(expected_full)} 字",
        )
        check("not_degraded", data.get("degraded") is False, data.get("state"))

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
