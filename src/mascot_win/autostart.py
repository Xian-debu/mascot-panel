"""开机自启：只写 HKCU\\...\\Run 一个值，不碰计划任务、不碰系统服务。

取舍：
- HKCU Run 是用户级、可随时删除、无需管理员权限；卸载/回滚只需删一个值。
- 不写 Startup 快捷方式：快捷方式的目标路径会随版本目录变化，会让旧版本残留。
- 默认 **不启用**：安装脚本必须显式 --autostart，用户始终可 `mascot autostart off`。
"""

from __future__ import annotations

import sys
from typing import Any

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Mascot"


class AutostartError(RuntimeError):
    pass


def _winreg() -> Any:
    """winreg 只在 Windows 存在；返回 Any 以免非 Windows 上的类型检查误判。"""
    if sys.platform != "win32":
        raise AutostartError("autostart 仅支持 Windows")
    import winreg  # noqa: PLC0415 - 平台相关导入

    return winreg


def default_command(exe: str | None = None) -> str:
    """注册表里写的命令行：带引号的可执行路径（路径含空格时必须引号）。"""
    target = exe or sys.executable
    if not target.lower().endswith(".exe"):
        raise AutostartError(f"自启目标必须是 exe（当前 {target!r}）；请用打包版或显式 --exe")
    return f'"{target}"'


def is_enabled() -> bool:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def current_command() -> str:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return ""
    return str(value)


def enable(exe: str | None = None) -> str:
    winreg = _winreg()
    cmd = default_command(exe)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    return cmd


def disable() -> bool:
    """返回是否真的删掉了值（本来没开就是 False，不算错误）。"""
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AutostartError(f"删除自启失败: {exc}") from exc
    return True
