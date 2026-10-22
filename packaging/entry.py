"""PyInstaller 唯一入口：GUI 双击与命令行子命令共用同一个 exe。"""

from __future__ import annotations

import sys

from mascot_app.cli import main

if __name__ == "__main__":
    sys.exit(main())
