"""球的 PIL 绘制：呼吸光点 + 轨道微光，颜色全部来自设计 token。

旧实现把青色/琥珀/红散在绘制代码里，改主题色要改三处；这里只查 token。
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

from mascot_core.tokens import COLORS, hex_to_rgb, pixel_palette

SS = 4  # 超采样倍数，缩回后边缘抗锯齿

# 状态灯配色：state -> (token 名, alpha)
BADGE_COLORS: dict[str, tuple[str, int]] = {
    "idle": ("accent", 200),
    "working": ("accent", 255),
    "awaiting": ("amber", 255),
    "error": ("red", 255),
}


def _rgb(name: str) -> tuple[int, int, int]:
    return hex_to_rgb(COLORS[name])


def render_ball(size: int = 96, phase: float = 0.0, stuck: bool = False) -> Image.Image:
    """phase ∈ [0,1) 驱动呼吸；stuck=True 时画成琥珀色（等待用户）。"""
    pal = pixel_palette(6)
    accent = _rgb("amber") if stuck else pal.accent
    highlight = _rgb("text")
    px = size * SS
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = px / 2
    r = px * 0.34
    breathe = 0.5 + 0.5 * math.sin(phase * 2 * math.pi)

    # 外晕：三层递减 alpha 的圆
    for i, alpha in ((1.55, 26), (1.28, 40), (1.08, 68)):
        rr = r * i
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=(*accent, int(alpha)))

    # 主体
    d.ellipse([c - r, c - r, c + r, c + r], fill=(*accent, 235))

    # 高光与芯要“叠加”而不是“替换”像素，否则球心会变成半透明的灰点
    shine = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    hr = r * 0.55
    hx, hy = c - r * 0.3, c - r * 0.35
    sd.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(*highlight, int(40 + 60 * breathe)))
    cr = r * 0.22
    sd.ellipse([c - cr, c - cr, c + cr, c + cr], fill=(*highlight, 210))
    img = Image.alpha_composite(img, shine)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def render_badge(size: int = 18, state: str = "idle") -> Image.Image:
    """状态灯（docs/12 的 agent 状态灯）：idle/working/awaiting/error。"""
    name, alpha = BADGE_COLORS.get(state, BADGE_COLORS["idle"])
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size * SS - 1, size * SS - 1], fill=(*_rgb(name), alpha))
    return img.resize((size, size), Image.Resampling.LANCZOS)
