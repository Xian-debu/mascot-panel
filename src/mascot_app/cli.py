"""mascot CLI：run / doctor / ctl。

契约（照搬 win-admin 的实证做法）：
    stdout : 恰好一个 JSON 对象（UTF-8），无日志混入
    stderr : 人类可读诊断
    exit   : 0 成功 / 2 参数错 / 3 环境不满足 / 4 被拒 / 5 执行失败
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path

from mascot_app import __version__
from mascot_app.providers import make_provider
from mascot_core.config import Settings, default_config_path, load_settings

EXIT_OK = 0
EXIT_ARGS = 2
EXIT_ENV = 3
EXIT_DENIED = 4
EXIT_FAIL = 5

REQUIRED_MODULES = ("webview", "PIL", "pydantic_settings", "psutil")


def _emit(payload: dict, code: int) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return code


def _fail(code: str, msg: str, exit_code: int, extra: dict | None = None) -> int:
    payload: dict = {"ok": False, "code": code, "msg": msg}
    if extra:
        payload.update(extra)
    return _emit(payload, exit_code)


def _check(name: str, ok: bool, detail: str, critical: bool = True) -> dict:
    return {"name": name, "ok": ok, "detail": detail, "critical": critical}


def _state_dir(settings: Settings) -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "mascot"
    return Path.home() / ".mascot"


def collect_doctor(settings: Settings, probe: bool = True) -> tuple[list[dict], bool]:
    checks: list[dict] = []

    vi = sys.version_info
    checks.append(
        _check("python", vi >= (3, 11), f"{vi.major}.{vi.minor}.{vi.micro} (need >=3.11)")
    )

    missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    checks.append(_check("dependencies", not missing, "missing: " + ", ".join(missing) if missing else "all present"))

    cfg_path = default_config_path()
    checks.append(
        _check("config", True, f"{cfg_path} ({'found' if cfg_path.is_file() else 'absent, using defaults'})", critical=False)
    )

    state = _state_dir(settings)
    try:
        state.mkdir(parents=True, exist_ok=True)
        probe_file = state / ".write-probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        writable, detail = True, str(state)
    except OSError as exc:
        writable, detail = False, f"{state}: {exc}"
    checks.append(_check("state_dir_writable", writable, detail))

    checks.append(
        _check(
            "platform",
            True,
            f"{platform.system()} {platform.release()} ({platform.machine()})",
            critical=False,
        )
    )

    if probe:
        provider = make_provider(settings)
        health = provider.health()
        checks.append(
            _check(
                "provider",
                health.ok,
                f"{provider.name}: {health.state.value} {health.reason_code or ''}".strip(),
                critical=False,
            )
        )

    ok = all(c["ok"] for c in checks if c["critical"])
    return checks, ok


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    checks, ok = collect_doctor(settings, probe=not args.offline)
    payload = {
        "ok": ok,
        "data": {
            "version": __version__,
            "checks": checks,
            "settings": settings.model_dump(mode="json"),
        },
    }
    if not ok:
        payload["code"] = "ENV_UNMET"
        payload["msg"] = "critical checks failed: " + ", ".join(
            c["name"] for c in checks if c["critical"] and not c["ok"]
        )
        return _emit(payload, EXIT_ENV)
    return _emit(payload, EXIT_OK)


def cmd_run(args: argparse.Namespace) -> int:
    # M0 只做骨架；真正的窗口接线在 M1/M2。
    return _fail("ENV_NOT_READY", "M0 skeleton: run 将在 M2 接线（见 docs/14-progress.md）", EXIT_ENV)


def cmd_ctl(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    if args.action == "status":
        checks, ok = collect_doctor(settings, probe=False)
        return _emit(
            {"ok": True, "data": {"running": False, "pid": None, "state": "idle", "checks": checks}},
            EXIT_OK,
        )
    if args.action == "stop":
        return _emit({"ok": True, "data": {"stopped": False, "detail": "not running"}}, EXIT_OK)
    return _fail("ARG_BAD_ACTION", f"unknown ctl action: {args.action}", EXIT_ARGS)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mascot", description="天选姬桌宠（重构版）")
    p.add_argument("--version", action="version", version=f"mascot {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="环境体检（JSON）")
    d.add_argument("--config", help="显式配置文件路径")
    d.add_argument("--offline", action="store_true", help="不探测 provider")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("run", help="启动桌宠（M2 起可用）")
    r.add_argument("--config", help="显式配置文件路径")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("ctl", help="控制运行中的实例")
    c.add_argument("action", choices=["status", "stop"])
    c.add_argument("--config", help="显式配置文件路径")
    c.set_defaults(func=cmd_ctl)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse 的参数错误 -> 统一退出码 2
        return EXIT_ARGS if exc.code not in (0, None) else EXIT_OK
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 - CLI 边界，必须兜住并给出可读错误
        import traceback

        traceback.print_exc(file=sys.stderr)
        return _fail("EXEC_FAILED", str(exc), EXIT_FAIL)


if __name__ == "__main__":
    raise SystemExit(main())
