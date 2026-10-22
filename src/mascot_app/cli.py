"""mascot CLI：run / doctor / ctl。

契约（照搬 win-admin 的实证做法）：
    stdout : 恰好一个 JSON 对象（UTF-8），无日志混入
    stderr : 人类可读诊断
    exit   : 0 成功 / 2 参数错 / 3 环境不满足 / 4 被拒 / 5 执行失败
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from mascot_app import __version__, boot
from mascot_app.logging_setup import setup_logging
from mascot_app.providers import make_provider
from mascot_core import configfile, update, versions
from mascot_core.config import HOT_FIELDS, Settings, default_config_path, load_settings

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
    config_path = Path(args.config) if args.config else default_config_path()
    settings = load_settings(config_path if config_path.is_file() else None)
    if args.provider:
        settings.provider = args.provider
    if args.allow_offline is not None:
        settings.allow_offline = args.allow_offline
    if args.provider_url:
        settings.provider_base_url = args.provider_url
    setup_logging(settings.log_dir, settings.log_level)

    try:
        from mascot_app.runtime import Runtime
        from mascot_win import win32
        from mascot_win.single import AlreadyRunning, SingleInstance
    except Exception as exc:  # noqa: BLE001 - 非 Windows 平台上导入即失败
        return _fail("ENV_UNSUPPORTED", f"run 仅支持 Windows: {exc}", EXIT_ENV)

    win32.enable_dpi_awareness()
    instance = SingleInstance()
    try:
        if not instance.acquire():
            return _fail("ALREADY_RUNNING", "已有 mascot 实例在运行（命名互斥体）", EXIT_ENV)
    except Exception as exc:  # noqa: BLE001
        return _fail("ENV_UNSUPPORTED", f"无法创建单实例互斥体: {exc}", EXIT_ENV)

    provider = make_provider(settings)
    pinned = {
        name
        for name, value in (
            ("provider", args.provider),
            ("allow_offline", args.allow_offline),
            ("provider_base_url", args.provider_url),
        )
        if value is not None
    }
    runtime = Runtime(settings, provider, config_path=config_path, pinned=pinned)
    try:
        runtime.run(
            duration_s=args.duration,
            demo=args.demo,
            screenshot=args.screenshot,
            gui=args.gui,
        )
    except AlreadyRunning:
        return _fail("ALREADY_RUNNING", "已有 mascot 实例在运行", EXIT_ENV)
    except KeyboardInterrupt:
        pass
    finally:
        instance.release()
    return _emit({"ok": True, "data": runtime.snapshot()}, EXIT_OK)


def _running_pid() -> int | None:
    """pid 文件 + 进程存活 + 进程名核对（防止 pid 复用误判）。"""
    try:
        import psutil

        from mascot_win.single import pid_file_path
    except Exception:  # noqa: BLE001
        return None
    try:
        with open(pid_file_path(), encoding="utf-8") as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return None
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return None
        cmdline = " ".join(proc.cmdline()).lower()
    except Exception:  # noqa: BLE001 - 进程已经没了
        return None
    return pid if "mascot" in cmdline else None


def _read_state_json() -> dict | None:
    try:
        from mascot_win.single import state_dir
    except Exception:  # noqa: BLE001
        return None
    try:
        return json.loads((Path(state_dir()) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _send_control(cmd: str, **extra: str) -> bool:
    try:
        from mascot_win.single import state_dir
    except Exception:  # noqa: BLE001
        return False
    try:
        path = Path(state_dir()) / "control.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cmd": cmd, **extra}, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


def cmd_ctl(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    pid = _running_pid()
    if args.action == "status":
        checks, _ok = collect_doctor(settings, probe=False)
        state = _read_state_json() or {}
        return _emit(
            {
                "ok": True,
                "data": {
                    "running": pid is not None,
                    "pid": pid,
                    "state": state.get("state", "stopped" if pid is None else "unknown"),
                    "degraded": state.get("degraded", False),
                    "provider": state.get("provider"),
                    "provider_detail": state.get("provider_detail", ""),
                    "paused": state.get("paused", False),
                    "dnd": state.get("dnd", False),
                    "pet": state.get("pet"),
                    "uptime_s": state.get("uptime_s"),
                    "sending": state.get("sending", False),
                    "streaming": state.get("streaming", {"active": False, "text": ""}),
                    "messages": state.get("messages", []),
                    "checks": checks,
                },
            },
            EXIT_OK,
        )
    if args.action == "send":
        if pid is None:
            return _fail("NOT_RUNNING", "没有运行中的实例", EXIT_ENV)
        text = (args.text or "").strip()
        if not text:
            return _fail("EMPTY_TEXT", "消息为空", EXIT_ARGS)
        if not _send_control("send", text=text):
            return _fail("IPC_FAILED", "控制文件写入失败", EXIT_FAIL)
        return _emit({"ok": True, "data": {"sent": "send", "pid": pid}}, EXIT_OK)
    if args.action == "clear-history":
        if pid is None:
            return _fail("NOT_RUNNING", "没有运行中的实例", EXIT_ENV)
        if not _send_control("clear_history"):
            return _fail("IPC_FAILED", "控制文件写入失败", EXIT_FAIL)
        return _emit({"ok": True, "data": {"sent": "clear_history", "pid": pid}}, EXIT_OK)
    if args.action == "cancel-send":
        if pid is None:
            return _fail("NOT_RUNNING", "没有运行中的实例", EXIT_ENV)
        if not _send_control("cancel_send"):
            return _fail("IPC_FAILED", "控制文件写入失败", EXIT_FAIL)
        return _emit({"ok": True, "data": {"sent": "cancel_send", "pid": pid}}, EXIT_OK)
    if args.action in ("to-ball", "to-panel", "pause", "resume", "dnd"):
        if pid is None:
            return _fail("NOT_RUNNING", "没有运行中的实例", EXIT_ENV)
        if args.action == "dnd":
            value = (args.value or "on").strip().lower()
            if value not in ("on", "off"):
                return _fail("ARG_BAD_VALUE", f"dnd 只接受 on/off，收到 {value}", EXIT_ARGS)
            cmd = "dnd_on" if value == "on" else "dnd_off"
        else:
            cmd = {
                "to-ball": "to_ball",
                "to-panel": "to_panel",
                "pause": "pause",
                "resume": "resume",
            }[args.action]
        if not _send_control(cmd):
            return _fail("IPC_FAILED", "控制文件写入失败", EXIT_FAIL)
        return _emit({"ok": True, "data": {"sent": cmd, "pid": pid}}, EXIT_OK)
    if args.action == "stop":
        if pid is None:
            return _emit({"ok": True, "data": {"stopped": False, "detail": "not running"}}, EXIT_OK)
        try:
            from mascot_app.runtime import PANEL_TITLE
            from mascot_win import win32

            hwnd = win32.find_window(PANEL_TITLE, timeout_s=1.0)
            if hwnd:
                win32.post_close(hwnd)
        except Exception as exc:  # noqa: BLE001 - 平台不支持时退化为报错
            return _fail("STOP_FAILED", str(exc), EXIT_FAIL)
        return _emit({"ok": True, "data": {"stopped": True, "pid": pid, "method": "wm_close"}}, EXIT_OK)
    return _fail("ARG_BAD_ACTION", f"unknown ctl action: {args.action}", EXIT_ARGS)


def cmd_autostart(args: argparse.Namespace) -> int:
    try:
        from mascot_win import autostart
    except Exception as exc:  # noqa: BLE001
        return _fail("ENV_UNSUPPORTED", f"autostart 仅支持 Windows: {exc}", EXIT_ENV)
    try:
        if args.action == "status":
            return _emit(
                {
                    "ok": True,
                    "data": {"enabled": autostart.is_enabled(), "command": autostart.current_command()},
                },
                EXIT_OK,
            )
        if args.action == "on":
            command = autostart.enable(args.exe)
            return _emit({"ok": True, "data": {"enabled": True, "command": command}}, EXIT_OK)
        removed = autostart.disable()
        return _emit({"ok": True, "data": {"enabled": False, "removed": removed}}, EXIT_OK)
    except autostart.AutostartError as exc:
        return _fail("AUTOSTART_FAILED", str(exc), EXIT_ENV)


def _app_dir(override: str | None) -> Path:
    """已安装版本目录：默认 %LOCALAPPDATA%/mascot/app。"""
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) / "mascot" if local else Path.home() / ".mascot"
    return base / "app"


def _infer_version(source: Path) -> str:
    """从源目录/zip 名或 exe 的 --version 输出推断版本号。"""
    name = source.stem if source.is_file() else source.name
    if versions.is_version_name(name):
        return name
    exe = source / "mascot.exe"
    if exe.is_file():
        with contextlib.suppress(OSError, IndexError):
            proc = subprocess.run(
                [str(exe), "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            parts = (proc.stdout or "").replace("mascot", " ").split()
            if parts and versions.is_version_name(parts[-1]):
                return parts[-1]
    raise ValueError("推断不出版本号，请用 --version 指定（如 --version 0.2.0）")


def _stop_running_instance() -> bool:
    """升级前停掉正在跑的实例（Windows 会锁住正在使用的 exe/dll）。"""
    pid = _running_pid()
    if pid is None:
        return False
    _send_control("stop")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if _running_pid() is None:
            return True
        time.sleep(0.2)
    return True


def cmd_update(args: argparse.Namespace) -> int:
    """就地升级：装到 app/<version>，原子切 current.txt，回收旧目录。"""
    app_dir = _app_dir(args.app_dir)
    source = Path(args.source)
    try:
        version = args.target_version or _infer_version(source)
        kind = update.source_kind(source)
    except ValueError as exc:
        return _fail("UPDATE_SOURCE", str(exc), EXIT_ARGS)
    stopped = False if args.dry_run else _stop_running_instance()
    try:
        res = update.install(
            source,
            app_dir,
            version,
            keep=args.keep,
            dry_run=args.dry_run,
            force=args.force,
        )
    except ValueError as exc:
        return _fail("UPDATE_REJECTED", str(exc), EXIT_ARGS)
    except OSError as exc:
        return _fail("UPDATE_FAILED", str(exc), EXIT_FAIL)
    res["kind"] = kind
    res["stopped"] = stopped
    res["restart_hint"] = "mascot.exe run"
    return _emit({"ok": True, "data": res}, EXIT_OK)

def cmd_versions(args: argparse.Namespace) -> int:
    """列出/回收已安装的版本目录（current 永不删）。"""
    app_dir = _app_dir(args.app_dir)
    data: dict = {"app_dir": str(app_dir), "current": versions.read_current(app_dir)}
    data["versions"] = versions.list_versions(app_dir)
    data["total_bytes"] = sum(int(row["size_bytes"]) for row in data["versions"])
    if args.prune:
        data["prune"] = versions.prune_versions(
            app_dir, keep=args.keep, dry_run=args.dry_run
        )
        data["versions"] = versions.list_versions(app_dir)
    return _emit({"ok": True, "data": data}, EXIT_OK)


def cmd_config(args: argparse.Namespace) -> int:
    """配置文件的读/写/路径。写回只动一个键，其它键原样保留。"""
    path = Path(args.config) if args.config else default_config_path()
    action = args.action
    try:
        if action == "path":
            return _emit({"ok": True, "data": {"path": str(path), "exists": path.is_file()}}, EXIT_OK)
        if action == "show":
            settings = load_settings(path if path.is_file() else None)
            return _emit(
                {
                    "ok": True,
                    "data": {
                        "path": str(path),
                        "exists": path.is_file(),
                        "file": configfile.read_config_file(path),
                        "effective": settings.model_dump(mode="json"),
                    },
                },
                EXIT_OK,
            )
        if action == "get":
            key = args.key or ""
            if key not in Settings.model_fields:
                return _fail("UNKNOWN_KEY", "unknown config key: " + key, EXIT_ARGS)
            settings = load_settings(path if path.is_file() else None)
            value = getattr(settings, key)
            return _emit({"ok": True, "data": {"key": key, "value": _jsonable(value)}}, EXIT_OK)
        if action == "set":
            key = args.key or ""
            raw = args.value
            if raw is None:
                return _fail("MISSING_VALUE", "config set needs a value", EXIT_ARGS)
            target, value = configfile.set_config_value(key, raw, path)
            return _emit(
                {"ok": True, "data": {"path": str(target), "key": key, "value": _jsonable(value),
                                      "hot": key in HOT_FIELDS,
                                      "restart_required": key not in HOT_FIELDS}},
                EXIT_OK,
            )
        if action == "unset":
            key = args.key or ""
            removed = configfile.unset_config_value(key, path)
            return _emit(
                {"ok": True, "data": {"path": str(path), "key": key, "removed": removed,
                                      "hot": key in HOT_FIELDS,
                                      "restart_required": key not in HOT_FIELDS}},
                EXIT_OK,
            )
    except ValueError as exc:
        return _fail("BAD_VALUE", str(exc), EXIT_ARGS)
    except OSError as exc:
        return _fail("WRITE_FAILED", str(exc), EXIT_FAIL)
    return _fail("BAD_ACTION", "unknown config action", EXIT_ARGS)


def _jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mascot", description="天选姬桌宠（重构版）")
    p.add_argument("--version", action="version", version=f"mascot {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="环境体检（JSON）")
    d.add_argument("--config", help="显式配置文件路径")
    d.add_argument("--offline", action="store_true", help="不探测 provider")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("run", help="启动桌宠")
    r.add_argument("--config", help="显式配置文件路径")
    r.add_argument("--provider", choices=["auto", "legacy", "wsl", "null"], help="覆盖跨环境 provider")
    r.add_argument(
        "--provider-url",
        help="覆盖 provider 地址（WSL→Windows 互操作会过滤环境变量，验收时必须走参数）",
    )
    r.add_argument("--duration", type=float, default=0.0, help="运行多少秒后自动退出（验收用）")
    r.add_argument("--demo", action="store_true", help="自动演示：2s 收球、6s 回面板（验收用）")
    r.add_argument("--screenshot", help="运行中截图保存路径（验收用）")
    r.add_argument("--gui", choices=["edgechromium", "mshtml"], help="强制 GUI 后端")
    r.add_argument(
        "--allow-offline",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="provider 不可达时是否允许离线运行",
    )
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("autostart", help="开机自启（HKCU Run，可随时关闭）")
    a.add_argument("action", choices=["on", "off", "status"])
    a.add_argument("--exe", help="自启目标 exe（默认当前可执行文件）")
    a.set_defaults(func=cmd_autostart)

    cf = sub.add_parser("config", help="配置文件：查看 / 修改 / 路径")
    cf.add_argument("action", choices=["path", "show", "get", "set", "unset"])
    cf.add_argument("key", nargs="?", help="配置键（Settings 字段名）")
    cf.add_argument("value", nargs="?", help="set 的新值")
    cf.add_argument("--config", help="显式配置文件路径")
    cf.set_defaults(func=cmd_config)

    v = sub.add_parser("versions", help="已安装版本目录：列举 / 回收旧版本")
    v.add_argument("--prune", action="store_true", help="回收旧版本目录")
    v.add_argument("--keep", type=int, default=2, help="保留几个版本（含 current，默认 2）")
    v.add_argument("--dry-run", action="store_true", help="prune 只报告不删除")
    v.add_argument("--app-dir", help="覆盖 app 目录（验收用）")
    v.set_defaults(func=cmd_versions)

    u = sub.add_parser("update", help="就地升级：从本地目录或 zip 安装新版本")
    u.add_argument("--from", dest="source", required=True, help="含 mascot.exe 的目录，或 .zip")
    u.add_argument("--version", dest="target_version", help="新版本号（默认从源目录名或 exe --version 推断）")
    u.add_argument("--keep", type=int, default=2, help="装完保留几个版本（含新版本，默认 2）")
    u.add_argument("--dry-run", action="store_true", help="只报计划，不动磁盘")
    u.add_argument("--force", action="store_true", help="允许覆盖同一版本")
    u.add_argument("--app-dir", help="覆盖 app 目录（验收用）")
    u.set_defaults(func=cmd_update)

    c = sub.add_parser("ctl", help="控制运行中的实例")
    c.add_argument(
        "action",
        choices=[
            "status", "stop", "to-ball", "to-panel", "send", "cancel-send",
            "clear-history", "pause", "resume", "dnd",
        ],
    )
    c.add_argument("--text", default="", help="send 动作要发送的文本")
    c.add_argument("value", nargs="?", help="dnd 的 on/off")
    c.add_argument("--config", help="显式配置文件路径")
    c.set_defaults(func=cmd_ctl)
    return p


def main(argv: list[str] | None = None) -> int:
    boot.mark("cli_main")
    # 双击 exe（无参数）时当作 GUI 启动：默认 run，并藏掉随之弹出的控制台窗口。
    # 同一个 exe 仍支持命令行子命令 —— 打包只出一个文件，用户只有一个入口。
    args_in = list(sys.argv[1:]) if argv is None else list(argv)
    launched_from_gui = not args_in
    if launched_from_gui:
        args_in = ["run"]
        with contextlib.suppress(Exception):
            from mascot_win.win32 import hide_console

            hide_console()
    parser = build_parser()
    try:
        args = parser.parse_args(args_in)
    except SystemExit as exc:  # argparse 的参数错误 -> 统一退出码 2
        return EXIT_ARGS if exc.code not in (0, None) else EXIT_OK
    # Windows 控制台默认 GBK：管道/互操作场景下会输出乱码，统一强制 UTF-8
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 - CLI 边界，必须兜住并给出可读错误
        import traceback

        traceback.print_exc(file=sys.stderr)
        return _fail("EXEC_FAILED", str(exc), EXIT_FAIL)


if __name__ == "__main__":
    raise SystemExit(main())
