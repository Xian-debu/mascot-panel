"""自启命令拼装：纯字符串逻辑，任何平台都能测。"""

from __future__ import annotations

import pytest

from mascot_win.autostart import AutostartError, default_command


def test_default_command_quotes_exe_path() -> None:
    assert default_command(r"C:\Program Files\Mascot\mascot.exe") == '"C:\\Program Files\\Mascot\\mascot.exe"'


def test_default_command_rejects_non_exe() -> None:
    with pytest.raises(AutostartError):
        default_command(r"C:\Python311\python.exe"[0:-4])


def test_registry_helpers_fail_loudly_off_windows() -> None:
    import sys

    if sys.platform == "win32":
        pytest.skip("Windows 上由真机验收覆盖")
    from mascot_win import autostart

    with pytest.raises(AutostartError):
        autostart.is_enabled()
