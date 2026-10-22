"""测试公共夹具：把状态目录隔离到 tmp（避免读写真实 ~/.mascot）。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path, monkeypatch):
    """Runtime 的状态目录优先读 LOCALAPPDATA；测试里指到 tmp，避免历史/状态互相污染。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
