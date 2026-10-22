"""M22 验收：clear-history 对「后端 history」也生效（清空后重启不复活）。

假 legacy 后端固定返回两条旧消息（/api/pet/news）：
1. 启动 -> 面板从后端读到这两条；
2. ctl clear-history -> 面板空，runtime.json 记下被清消息的 id；
3. 重启 -> 后端照样返回这两条，但按 id 过滤，面板仍是空；
4. 后端新增第 3 条 -> 重启后只显示这条新的。
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
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
STATE = STATE_DIR / "state.json"
HISTORY = STATE_DIR / "history.json"
RUNTIME = STATE_DIR / "runtime.json"
# venv 的 python.exe 是转发器（pid 不是桌宠 pid），验收直连真解释器
PYTHON = str(getattr(sys, "_base_executable", sys.executable))

NEWS: list[dict] = []


def read_json(path: Path) -> dict:
    with contextlib.suppress(Exception):
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def texts(snap: dict) -> list[str]:
    return [m.get("text", "") for m in snap.get("messages", [])]


def wait_until(pred, timeout: float = 25.0) -> dict:
    t0 = time.time()
    snap = read_json(STATE)
    while time.time() - t0 < timeout:
        snap = read_json(STATE)
        if pred(snap):
            return snap
        time.sleep(0.05)
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
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/pet/status"):
            body = {"status": "ok", "engine": "ready"}
        elif self.path.startswith("/api/pet/news"):
            body = {"code": 202000, "data": list(NEWS)}
        elif self.path.startswith("/api/pet/health"):
            body = {"ok": True}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: object) -> None:
        pass


def fresh_state() -> None:
    for path in (STATE, HISTORY, RUNTIME, STATE_DIR / "control.json", STATE_DIR / "mascot.pid"):
        with contextlib.suppress(OSError):
            path.unlink()


def stop(proc: subprocess.Popen) -> dict:
    res: dict = {}
    for _ in range(6):
        _code, res = cli("ctl", "stop")
        try:
            proc.wait(timeout=3.0)
            return res
        except subprocess.TimeoutExpired:
            continue
    proc.kill()
    proc.wait(timeout=5)
    return res


def launch(url: str, env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        [
            PYTHON, "-m", "mascot_app.cli", "run",
            "--provider", "auto",
            "--provider-url", url,
        ],
        cwd=str(ROOT),
        env=env,
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    checks: dict[str, object] = {}
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    purelib = sysconfig.get_paths()["purelib"]
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [purelib, env.get("PYTHONPATH", "")]))

    NEWS.extend(
        [
            {"id": 1, "title": "主人: 旧问题", "description": "旧问题甲"},
            {"id": 2, "title": "天选姬: 旧回答", "description": "旧回答乙"},
        ]
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        # ---- 第一轮：后端历史被读到 ----
        fresh_state()
        proc = launch(url, env)
        try:
            snap = wait_until(lambda s: len(s.get("messages", [])) >= 2, 30)
            got = texts(snap)
            checks["backend_history_loaded"] = "旧问题甲" in got and "旧回答乙" in got
            roles = [m.get("role") for m in snap.get("messages", [])]
            checks["roles_from_titles"] = roles[:2] == ["user", "assistant"]

            _code, res = cli("ctl", "clear-history")
            checks["clear_sent"] = res.get("ok") is True
            snap = wait_until(lambda s: s.get("messages") == [], 10)
            checks["cleared_in_memory"] = snap.get("messages") == []
            time.sleep(0.5)
            runtime = read_json(RUNTIME)
            cleared = runtime.get("cleared_history_ids", [])
            checks["cleared_ids_saved"] = "legacy-1" in cleared and "legacy-2" in cleared
            checks["history_file_cleared"] = read_json(HISTORY).get("messages") == []

            stop(proc)
            checks["exit_after_clear"] = proc.returncode == 0
        finally:
            if proc.poll() is None:
                proc.kill()

        # ---- 第二轮：后端仍返回旧消息，不再复活 ----
        with contextlib.suppress(OSError):
            (STATE_DIR / "control.json").unlink()
        proc = launch(url, env)
        try:
            snap = wait_until(lambda s: s.get("state") == "idle", 30)
            time.sleep(1.5)
            snap = read_json(STATE)
            checks["not_resurrected"] = snap.get("messages") == []

            stop(proc)
            checks["exit_after_restart"] = proc.returncode == 0
        finally:
            if proc.poll() is None:
                proc.kill()

        # ---- 第三轮：后端新增一条，只显示新的 ----
        NEWS.append({"id": 3, "title": "天选姬: 新回答", "description": "新回答丙"})
        with contextlib.suppress(OSError):
            (STATE_DIR / "control.json").unlink()
        proc = launch(url, env)
        try:
            snap = wait_until(lambda s: "新回答丙" in texts(s), 30)
            got = texts(snap)
            checks["new_item_shown"] = "新回答丙" in got
            checks["old_items_still_hidden"] = "旧问题甲" not in got and "旧回答乙" not in got
            checks["instance_alive"] = proc.poll() is None
            stop(proc)
            checks["stop_ok"] = proc.returncode == 0
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
