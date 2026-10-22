"""M17 验收：config 写回保留注释 / 未知键 / [table] 段。

全部在临时文件上做（--config 显式路径），不碰真实配置：
1. 手写带注释、未知键、[extra] 表的配置，config set fps 20 后注释与未知键仍在、fps 变 20
2. 文件仍是合法 TOML（tomllib 能读）
3. config get fps 返回 20
4. config unset fps 删掉键但保留注释，退出码 0
5. 非法值 fps=999 被拒（退出码 2）且文件未被改动
"""
import contextlib
import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASE = (
    "# 我的手写配置\n"
    "fps = 12  # 流畅优先\n"
    "\n"
    "# mascot 不认识的键，写回时不许删\n"
    'custom_thing = "keep me"\n'
    "\n"
    "[extra]\n"
    'note = "表里的也别动"\n'
)


def cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mascot_app.cli", "config", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    with contextlib.suppress(Exception):
        return proc.returncode, json.loads(proc.stdout)
    return proc.returncode, {"raw": proc.stdout + proc.stderr}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.toml"
        cfg.write_text(BASE, encoding="utf-8")

        code, out = cli("set", "fps", "20", "--config", str(cfg))
        text = cfg.read_text(encoding="utf-8")
        checks["set_exit_0"] = code == 0 and out.get("ok") is True
        checks["comment_kept"] = "# 我的手写配置" in text and "# 流畅优先" in text
        checks["unknown_key_kept"] = 'custom_thing = "keep me"' in text
        checks["table_kept"] = "[extra]" in text and 'note = "表里的也别动"' in text
        data = {}
        with contextlib.suppress(Exception):
            data = tomllib.loads(text)
        checks["still_valid_toml"] = data.get("fps") == 20 and data.get("custom_thing") == "keep me"
        checks["table_value_intact"] = data.get("extra", {}).get("note") == "表里的也别动"

        code, out = cli("get", "fps", "--config", str(cfg))
        checks["get_returns_20"] = code == 0 and out.get("data", {}).get("value") == 20

        before = cfg.read_text(encoding="utf-8")
        code, out = cli("set", "fps", "999", "--config", str(cfg))
        checks["bad_value_rejected"] = code == 2 and out.get("ok") is False
        checks["file_untouched_on_reject"] = cfg.read_text(encoding="utf-8") == before

        code, out = cli("unset", "fps", "--config", str(cfg))
        text = cfg.read_text(encoding="utf-8")
        checks["unset_exit_0"] = code == 0 and out.get("data", {}).get("removed") is True
        checks["key_removed"] = "fps =" not in text
        # 行尾注释属于那一行，键删了注释跟着走；独立注释行必须还在
        checks["comments_survived_unset"] = "# 我的手写配置" in text and "custom_thing" in text
        checks["exit_code"] = 0

    ok = all(value is True for key, value in checks.items() if key != "exit_code") and (
        checks.get("exit_code") == 0
    )
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
