"""命中测试：纯函数，喂屏幕坐标与一组矩形，回答"点到谁了"。

约定：regions 按**自下而上**排列（列表末尾是顶层），返回最后一个包含该点的区域。
这样可以表达"球压在面板上"这类层叠，而不用在调用方写分支。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mascot_core.geometry import Rect


class HitKind(StrEnum):
    NONE = "none"
    PANEL = "panel"
    BALL = "ball"


@dataclass(frozen=True, slots=True)
class HitRegion:
    kind: HitKind
    rect: Rect


def hit_test(px: float, py: float, regions: list[HitRegion]) -> HitKind:
    """返回命中的最上层区域；没有命中返回 HitKind.NONE。

    纯函数：同样的输入永远同样的输出，不读全局状态 —— 这样能被平台层
    的鼠标钩子反复调用而不产生副作用（见 docs/08 R-02）。
    """
    for region in reversed(regions):
        if region.rect.contains(px, py):
            return region.kind
    return HitKind.NONE
