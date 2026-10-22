"""渲染快照画廊：测试与文档共用同一个用例表（避免两处漂移）。"""

from __future__ import annotations

import time

from PIL import Image

from mascot_render.ball import render_badge, render_ball
from mascot_render.clock import render_clock


def snapshot_cases() -> dict[str, Image.Image]:
    """返回 {用例名: 图像}；改名或改绘制都会让快照测试要求更新基线。"""
    cases: dict[str, Image.Image] = {}
    for phase in (0.0, 0.25, 0.5, 0.75):
        cases[f"ball-phase-{phase:.2f}"] = render_ball(96, phase=phase)
    cases["ball-stuck"] = render_ball(96, phase=0.0, stuck=True)
    for state in ("idle", "working", "awaiting", "error"):
        cases[f"badge-{state}"] = render_badge(18, state=state)
    for label, hour, minute in (("1010", 10, 10), ("1545", 15, 45), ("1200", 12, 0)):
        cases[f"clock-{label}"] = render_clock(
            128, now=time.struct_time((2026, 10, 22, hour, minute, 0, 3, 295, -1)), now_ts=0.0
        )
    cases["clock-stuck"] = render_clock(
        128, now=time.struct_time((2026, 10, 22, 10, 10, 0, 3, 295, -1)), now_ts=0.0, stuck=True
    )
    return cases


def contact_sheet(cell: int = 112, cols: int = 5, bg: tuple[int, int, int] = (14, 17, 22)) -> Image.Image:
    """把全部用例铺成一张暗底拼图，供人工一眼检查（evidence 用）。"""
    cases = list(snapshot_cases().values())
    rows = (len(cases) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (*bg, 255))
    for i, img in enumerate(cases):
        x = (i % cols) * cell + (cell - img.width) // 2
        y = (i // cols) * cell + (cell - img.height) // 2
        sheet.alpha_composite(img, (x, y))
    return sheet
