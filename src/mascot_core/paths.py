"""状态目录解析（A3/M33）。

单一真源：所有落盘文件（config.toml / runtime.json / history.json / state.json /
control.json / mascot.pid / logs）都从这里取目录，优先级：

1. MASCOT_STATE_DIR（开发/验收用，显式隔离）
2. %LOCALAPPDATA%/mascot（Windows 正常用户目录）
3. ~/.mascot（无 LOCALAPPDATA 时的回退，Linux CI 也走这里）
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_OVERRIDE = "MASCOT_STATE_DIR"


def state_dir() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "mascot"
    return Path.home() / ".mascot"
