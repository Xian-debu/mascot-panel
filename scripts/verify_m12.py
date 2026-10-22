"""M12 验收：配置写回 + 运行态开关跨重启记住。

- config set fps 20 → config.toml 落盘，config get fps 读回 20，doctor 随之 20
- config set 未知键 / 超范围值必须被拒（rc 2，且不落盘）
- 启动 → ctl dnd on / pause → ctl stop → 重启 → dnd/paused 仍为 true（runtime.json）
- ctl dnd off / resume → 收尾还原
"""
import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
STATE = LOCAL / "mascot" / "state.json"
CONFIG = LOCAL / "mascot" / "config.toml"
FLAGS = LOCAL / "mascot" / "runtime.json"


def read_json(path: Path) -> dict:
    for _ in range(50):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            time.sleep(0.1)
    return {}


def wait_for(pred, timeout=25.0) -> dict:
    t0 = time.time()
    snap = {}
    while time.time() - t0 < timeout:
        snap = read_json(STATE)
        if pred(snap):
            return snap
        time.sleep(0.1)
    return snap


def cli(*args: str) -> tuple[dict, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    try:
        return json.loads(proc.stdout), proc.returncode
    except Exception:
        return {"ok": False, "raw": proc.stdout + proc.stderr}, proc.returncode


def start() -> subprocess.Popen:
    with contextlib.suppress(OSError):
        STATE.unlink()
    with contextlib.suppress(OSError):
        (LOCAL / "mascot" / "control.json").unlink()
    return subprocess.Popen(
        [sys.executable, "-m", "mascot_app.cli", "run", "--provider", "null"], cwd=str(ROOT)
    )


def stop(proc: subprocess.Popen) -> int:
    cli("ctl", "stop")
    try:
        return proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    checks: dict[str, object] = {}

    # ---- 配置写回 -------------------------------------------------------
    payload, rc = cli("config", "set", "fps", "20")
    checks["config_set_ok"] = rc == 0 and payload.get("ok") is True
    checks["config_file_written"] = CONFIG.is_file() and "fps = 20" in CONFIG.read_text(encoding="utf-8")
    payload, rc = cli("config", "get", "fps")
    checks["config_get_roundtrip"] = payload.get("data", {}).get("value") == 20
    payload, rc = cli("config", "set", "nope", "1")
    checks["unknown_key_rejected"] = rc == 2 and payload.get("ok") is False
    payload, rc = cli("config", "set", "fps", "999")
    checks["out_of_range_rejected"] = rc == 2 and payload.get("ok") is False
    payload, rc = cli("config", "show")
    checks["show_effective_fps"] = payload.get("data", {}).get("effective", {}).get("fps") == 20

    # ---- 第一次运行：打开开关 -------------------------------------------
    proc = start()
    try:
        snap = wait_for(lambda s: s.get("state") == "tracking")
        checks["run1_tracking"] = snap.get("state")
        checks["run1_flags_default_off"] = snap.get("dnd") is False and snap.get("paused") is False
        cli("ctl", "dnd", "on")
        wait_for(lambda s: s.get("dnd") is True)
        cli("ctl", "pause")
        snap = wait_for(lambda s: s.get("paused") is True)
        checks["run1_both_on"] = snap.get("dnd") is True and snap.get("paused") is True
        checks["flags_file_written"] = FLAGS.is_file()
    finally:
        checks["run1_exit"] = stop(proc)

    # ---- 第二次运行：开关应被记住 ---------------------------------------
    proc = start()
    try:
        snap = wait_for(lambda s: s.get("state") in {"tracking", "idle"})
        checks["run2_restored_dnd"] = snap.get("dnd") is True
        checks["run2_restored_paused"] = snap.get("paused") is True
        cli("ctl", "dnd", "off")
        wait_for(lambda s: s.get("dnd") is False)
        cli("ctl", "resume")
        snap = wait_for(lambda s: s.get("paused") is False)
        checks["run2_flags_cleared"] = snap.get("dnd") is False and snap.get("paused") is False
    finally:
        checks["run2_exit"] = stop(proc)

    # ---- 收尾：删掉验收写入的配置键 -------------------------------------
    payload, rc = cli("config", "unset", "fps")
    checks["cleanup_config"] = rc == 0 and payload.get("data", {}).get("removed") is True

    ok = all(
        [
            checks["config_set_ok"],
            checks["config_file_written"],
            checks["config_get_roundtrip"],
            checks["unknown_key_rejected"],
            checks["out_of_range_rejected"],
            checks["show_effective_fps"],
            checks["run1_tracking"] == "tracking",
            checks["run1_flags_default_off"],
            checks["run1_both_on"],
            checks["flags_file_written"],
            checks["run1_exit"] == 0,
            checks["run2_restored_dnd"],
            checks["run2_restored_paused"],
            checks["run2_flags_cleared"],
            checks["run2_exit"] == 0,
            checks["cleanup_config"],
        ]
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
