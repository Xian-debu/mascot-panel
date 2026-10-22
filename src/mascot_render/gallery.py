"""渲染快照画廊：测试与文档共用同一个用例表（避免两处漂移）。"""

from __future__ import annotations

from PIL import Image

from mascot_render.ball import render_badge, render_ball


def snapshot_cases() -> dict[str, Image.Image]:
    """返回 {用例名: 图像}；改名或改绘制都会让快照测试要求更新基线。"""
    cases: dict[str, Image.Image] = {}
    for phase in (0.0, 0.25, 0.5, 0.75):
        cases[f"ball-phase-{phase:.2f}"] = render_ball(96, phase=phase)
    cases["ball-stuck"] = render_ball(96, phase=0.0, stuck=True)
    for state in ("idle", "working", "awaiting", "error"):
        cases[f"badge-{state}"] = render_badge(18, state=state)
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
