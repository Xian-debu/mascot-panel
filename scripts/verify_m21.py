"""M21 验收：health 探测独立短超时。

A. 没有后端时（auto 连探 legacy + wsl 两次）：降级横幅必须在 ~2s 级别出现，不再等 4s+。
B. 后端健康时（本脚本起一个假 legacy 后端）：health 走短超时也照样判 UP，状态不降级。
"""
import contextlib
import json
import os
import subprocess
import sys
import sysconfig
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# venv 的 python.exe 是「转发器」：它会再起一个真解释器，Popen 拿到的 pid 不是桌宠自己的 pid。
# 用 _base_executable + PYTHONPATH 直连真解释器，pid 文件、ctl stop、退出码才对得上。
PYTHON = str(getattr(sys, "_base_executable", sys.executable))
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
STATE = STATE_DIR / "state.json"


def read_state() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def wait_until(pred, timeout: float = 20.0) -> dict:
    t0 = time.time()
    snap = read_state()
    while time.time() - t0 < timeout:
        snap = read_state()
        if pred(snap):
            return snap
        time.sleep(0.02)
    return snap


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return proc.returncode, json.loads(proc.stdout)
    return proc.returncode, {"raw": proc.stdout + proc.stderr}


class StubHandler(BaseHTTPRequestHandler):
    requests: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(self.path)
        if self.path.startswith("/api/pet/status"):
            body = {"status": "ok", "engine": "ready"}
        elif self.path.startswith("/api/pet/news"):
            body = {"code": 202000, "data": []}
        elif self.path.startswith("/api/pet/health"):
            body = {"ok": True}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: object) -> None:
        pass


def stop(proc: subprocess.Popen, *extra: str, timeout: float = 12.0) -> dict:
    """ctl stop + 兜底：pid 还没写出来 / 窗口标题找不到时多试几次，最后才强杀。"""
    res: dict = {}
    for _ in range(5):
        _code, res = cli("ctl", "stop", *extra)
        try:
            proc.wait(timeout=2.5)
            return res
        except subprocess.TimeoutExpired:
            continue
    proc.kill()
    proc.wait(timeout=5)
    return res


def fresh_state() -> None:
    for path in (STATE, STATE_DIR / "control.json"):
        with contextlib.suppress(OSError):
            path.unlink()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    checks: dict[str, object] = {}
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    purelib = sysconfig.get_paths()["purelib"]
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [purelib, env.get("PYTHONPATH", "")]))

    # ---- A：没有后端 ----
    fresh_state()
    t0 = time.time()
    proc = subprocess.Popen(
        [PYTHON, "-m", "mascot_app.cli", "run", "--provider", "auto"],
        cwd=str(ROOT),
        env=env,
    )
    try:
        snap = wait_until(lambda s: bool(s.get("provider_detail")), 20)
        elapsed = time.time() - t0
        checks["degrade_fast"] = elapsed < 3.0
        checks["degrade_elapsed_s"] = round(elapsed, 2)
        checks["degraded_state"] = snap.get("state") == "degraded"
        checks["boot_mark_fast"] = int(snap.get("boot", {}).get("state_degraded", 99999)) < 3000
        checks["health_timeout_exposed"] = snap.get("settings", {}).get("health_timeout_s") == 0.8
        _code, res = cli("ctl", "stop")
        checks["stop_after_down"] = res.get("ok") is True
        proc.wait(timeout=15)
        checks["exit_code_down"] = proc.returncode == 0
    finally:
        if proc.poll() is None:
            proc.kill()

    # ---- B：假后端健康 ----
    StubHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        fresh_state()
        t0 = time.time()
        proc = subprocess.Popen(
            [
                PYTHON, "-m", "mascot_app.cli", "run",
                "--provider", "auto",
                "--provider-url", f"http://127.0.0.1:{port}",
            ],
            cwd=str(ROOT),
            env=env,
        )
        try:
            wait_until(lambda _s: bool(StubHandler.requests), 20)
            elapsed = time.time() - t0
            time.sleep(0.5)
            snap = read_state()
            checks["healthy_fast"] = elapsed < 3.0
            checks["healthy_elapsed_s"] = round(elapsed, 2)
            checks["not_degraded"] = snap.get("degraded") is False and snap.get("state") != "degraded"
            checks["stub_probed"] = any("/api/pet/status" in p for p in StubHandler.requests)
            checks["wsl_not_probed"] = not any("/api/pet/health" in p for p in StubHandler.requests)
            checks["instance_alive"] = proc.poll() is None
            res = stop(proc)
            checks["stop_ok"] = res.get("ok") is True and res.get("data", {}).get("stopped") is True
            checks["exit_code"] = proc.returncode == 0
        finally:
            if proc.poll() is None:
                proc.kill()
    finally:
        server.shutdown()
        server.server_close()

    failed = [k for k, v in checks.items() if v is False]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
