"""像素快照测试：球与状态灯的绘制稳定性。

基线由 scripts/make_baselines.py 生成并提交。允许极小误差：
不同 Pillow 版本 / CPU 的 LANCZOS 抗锯齿会有 ±1 的抖动。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from mascot_render.gallery import snapshot_cases

BASELINE = Path(__file__).parent / "baseline"
MEAN_TOL = 2.0  # 每通道平均绝对误差（0-255）
MAX_TOL = 48  # 单像素最大误差（抗锯齿边缘）


def _diff_stats(actual: Image.Image, expected: Image.Image) -> tuple[float, int]:
    diff = ImageChops.difference(actual.convert("RGBA"), expected.convert("RGBA"))
    stat = ImageStat.Stat(diff)
    mean = sum(stat.mean) / len(stat.mean)
    max_diff = max(band[1] for band in stat.extrema)
    return mean, max_diff


@pytest.mark.parametrize("name", sorted(snapshot_cases()))
def test_snapshot_matches_baseline(name: str) -> None:
    path = BASELINE / f"{name}.png"
    assert path.exists(), f"缺少基线 {path}，先运行 uv run python scripts/make_baselines.py"
    expected = Image.open(path)
    mean, max_diff = _diff_stats(snapshot_cases()[name], expected)
    assert mean <= MEAN_TOL, f"{name}: 平均误差 {mean:.2f} > {MEAN_TOL}"
    assert max_diff <= MAX_TOL, f"{name}: 单像素最大误差 {max_diff} > {MAX_TOL}"
