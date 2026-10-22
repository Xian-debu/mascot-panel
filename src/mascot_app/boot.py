"""启动计时（诊断用，不进业务逻辑）。

为什么需要：冷启动实测 4.34 s，DoD 是 ≤2 s。没有分段数据就只能猜。
每个里程碑记一次单调时钟，快照里带 boot 字段，measure_start.py 直接读。
"""

from __future__ import annotations

import time

T0 = time.monotonic()
_MARKS: dict[str, float] = {}


def mark(name: str) -> None:
    if name not in _MARKS:
        _MARKS[name] = round((time.monotonic() - T0) * 1000.0, 1)


def marks() -> dict[str, float]:
    return dict(_MARKS)
