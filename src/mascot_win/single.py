"""单实例：命名互斥体（R-04）。pid 文件只用于诊断，不参与判重。"""

from __future__ import annotations

import contextlib
import os

from mascot_core import paths
from mascot_win import win32

MUTEX_NAME = "Local\\Mascot.SingleInstance"


def state_dir() -> str:
    """与 mascot_core.paths.state_dir 同一真源（含 MASCOT_STATE_DIR 覆盖）。"""
    return str(paths.state_dir())


def pid_file_path() -> str:
    """诊断用 pid 文件（不参与判重，见 R-04）。"""
    return os.path.join(state_dir(), "mascot.pid")


class AlreadyRunning(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"another instance is running: {name}")
        self.name = name


class SingleInstance:
    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self._handle = 0
        self.already_running = False

    def acquire(self) -> bool:
        self._handle, self.already_running = win32.create_mutex(self.name)
        if self.already_running:
            win32.close_handle(self._handle)
            self._handle = 0
            return False
        pid_file = pid_file_path()
        try:
            os.makedirs(os.path.dirname(pid_file), exist_ok=True)
            with open(pid_file, "w", encoding="utf-8") as fh:
                fh.write(str(os.getpid()))
        except OSError:
            pass
        return True

    def release(self) -> None:
        win32.close_handle(self._handle)
        self._handle = 0
        with contextlib.suppress(OSError):
            os.unlink(pid_file_path())

    def __enter__(self) -> SingleInstance:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def ensure_single(name: str = MUTEX_NAME) -> SingleInstance:
    inst = SingleInstance(name)
    if not inst.acquire():
        raise AlreadyRunning(name)
    return inst
