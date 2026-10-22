from __future__ import annotations

from mascot_core.geometry import Rect
from mascot_core.hit import HitKind, HitRegion, hit_test


def test_hit_none() -> None:
    regions = [HitRegion(HitKind.PANEL, Rect(0, 0, 100, 100))]
    assert hit_test(500, 500, regions) is HitKind.NONE


def test_hit_panel() -> None:
    regions = [HitRegion(HitKind.PANEL, Rect(0, 0, 100, 100))]
    assert hit_test(50, 50, regions) is HitKind.PANEL


def test_topmost_wins() -> None:
    panel = HitRegion(HitKind.PANEL, Rect(0, 0, 100, 100))
    ball = HitRegion(HitKind.BALL, Rect(40, 40, 20, 20))
    assert hit_test(50, 50, [panel, ball]) is HitKind.BALL
    assert hit_test(10, 10, [panel, ball]) is HitKind.PANEL


def test_empty_regions() -> None:
    assert hit_test(1, 1, []) is HitKind.NONE
