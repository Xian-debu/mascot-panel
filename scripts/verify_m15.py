"""M15 验收：聊天记录跨重启保留 + 可清空。

无宠物启动（null provider，离线欢迎语）：
1. 发一条消息，面板里有它
2. 落盘到 %LOCALAPPDATA%/mascot/history.json
3. 杀掉重启：对话还在（欢迎语不重复、消息不重复）
4. ctl clear-history 清空：内存和文件都空了
5. 再重启：清空后不会"复活"
6. 退出码 0
"""
import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "mascot"
)
STATE = STATE_DIR / "state.json"
HISTORY = STATE_DIR / "history.json"
MARK = "记住这句话-M15"


def read_state() -> dict:
    with contextlib.suppress(Exception):
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def texts(snap: dict) -> list[str]:
    return [str(m.get("text", "")) for m in snap.get("messages", [])]


def wait_for(pred, timeout=25.0) -> dict:
    t0 = time.time()
    snap = {}
    while time.time() - t0 < timeout:
        snap = read_state()
        if pred(snap):
            return snap
        time.sleep(0.1)
    return snap


def ctl(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", "ctl", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return json.loads(proc.stdout)
    return {"ok": False, "raw": proc.stdout + proc.stderr}


def spawn() -> subprocess.Popen:
    env = dict(os.environ)
    env["MASCOT_PET_PROCESS_NAMES"] = '["__no_such_pet__.exe"]'
    env["MASCOT_PET_WINDOW_CLASS"] = "__no_such_class__"
    return subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"],
        cwd=str(ROOT),
        env=env,
    )


def start_fresh() -> subprocess.Popen:
    """每个实例都从"干净快照"开始等，否则会读到上一轮遗留的 state.json 而提前返回。"""
    for path in (STATE, STATE_DIR / "control.json"):
        with contextlib.suppress(OSError):
            path.unlink()
    proc = spawn()
    wait_for(lambda s: s.get("state") == "idle", 30)
    time.sleep(1.0)  # 等 history 线程合并完历史、control.json 启动清理结束
    return proc


def stop(proc: subprocess.Popen) -> int:
    ctl("stop")
    try:
        return proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    for path in (STATE, STATE_DIR / "control.json", HISTORY):
        with contextlib.suppress(OSError):
            path.unlink()

    checks: dict[str, object] = {}

    # ---- 第一轮：发消息 → 落盘 -------------------------------------------
    proc = start_fresh()
    try:
        checks["initial_greeting"] = texts(read_state())
        ctl("send", "--text", MARK)
        snap = wait_for(lambda s: MARK in texts(s), 15)
        checks["message_shown"] = MARK in texts(snap)
        time.sleep(1.0)
        checks["history_file_exists"] = HISTORY.is_file()
        raw = {}
        with contextlib.suppress(Exception):
            raw = json.loads(HISTORY.read_text(encoding="utf-8"))
        saved = [str(m.get("text", "")) for m in raw.get("messages", [])]
        checks["message_persisted"] = MARK in saved
    finally:
        code1 = stop(proc)
    checks["first_exit_code"] = code1

    # ---- 第二轮：重启恢复，且不重复 --------------------------------------
    proc = start_fresh()
    try:
        snap = wait_for(lambda s: MARK in texts(s), 15)
        msgs = texts(snap)
        checks["message_restored"] = MARK in msgs
        checks["restored_count"] = len(msgs)
        checks["no_duplicate_greeting"] = sum("离线模式" in t for t in msgs) == 1
        checks["no_duplicate_message"] = msgs.count(MARK) == 1
        # 重启后继续聊：新消息追加到已有记录后面
        checks["send2"] = ctl("send", "--text", "第二轮-M15")
        snap = wait_for(lambda s: "第二轮-M15" in texts(s), 20)
        checks["texts_after_send"] = texts(snap)
        msgs = texts(snap)
        checks["append_after_restore"] = "第二轮-M15" in msgs and MARK in msgs
        checks["still_no_duplicates"] = msgs.count(MARK) == 1

        # ---- 清空：内存与文件同时清 --------------------------------------
        ctl("clear-history")
        snap = wait_for(lambda s: len(s.get("messages", [])) == 0, 10)
        checks["cleared_in_memory"] = snap.get("messages", [None]) == []
        time.sleep(0.8)
        with contextlib.suppress(Exception):
            raw = json.loads(HISTORY.read_text(encoding="utf-8"))
        checks["cleared_on_disk"] = raw.get("messages", None) == []
    finally:
        code2 = stop(proc)
    checks["second_exit_code"] = code2

    # ---- 第三轮：清空后不复活 --------------------------------------------
    proc = start_fresh()
    try:
        msgs = texts(read_state())
        checks["not_resurrected"] = MARK not in msgs and "第二轮-M15" not in msgs
        checks["greeting_after_clear"] = msgs
    finally:
        code3 = stop(proc)
    checks["third_exit_code"] = code3

    ok = (
        checks.get("message_shown") is True
        and checks.get("history_file_exists") is True
        and checks.get("message_persisted") is True
        and checks.get("first_exit_code") == 0
        and checks.get("message_restored") is True
        and checks.get("no_duplicate_greeting") is True
        and checks.get("no_duplicate_message") is True
        and checks.get("append_after_restore") is True
        and checks.get("still_no_duplicates") is True
        and checks.get("cleared_in_memory") is True
        and checks.get("cleared_on_disk") is True
        and checks.get("second_exit_code") == 0
        and checks.get("not_resurrected") is True
        and checks.get("third_exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
