"""球的 PIL 绘制：呼吸光点 + 轨道微光，全部用设计 token 的颜色。"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

from mascot_core.tokens import pixel_palette

SS = 4  # 超采样倍数，缩回后边缘抗锯齿


def render_ball(size: int = 96, phase: float = 0.0, stuck: bool = False) -> Image.Image:
    """phase ∈ [0,1) 驱动呼吸；stuck=True 时画成琥珀色（等待用户）。"""
    pal = pixel_palette(6)
    accent = (0xE3, 0xB3, 0x41) if stuck else pal.accent
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
    # 高光偏左上
    hr = r * 0.55
    hx, hy = c - r * 0.3, c - r * 0.35
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255, int(40 + 60 * breathe)))
    # 芯
    cr = r * 0.22
    d.ellipse([c - cr, c - cr, c + cr, c + cr], fill=(255, 255, 255, 210))

    return img.resize((size, size), Image.Resampling.LANCZOS)


def render_badge(size: int = 18, state: str = "idle") -> Image.Image:
    """状态灯（docs/12 的 agent 状态灯）：idle/working/awaiting/error。"""
    colors = {
        "idle": (0x56, 0xD4, 0xDD, 200),
        "working": (0x56, 0xD4, 0xDD, 255),
        "awaiting": (0xE3, 0xB3, 0x41, 255),
        "error": (0xF8, 0x51, 0x49, 255),
    }
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = colors.get(state, colors["idle"])
    d.ellipse([0, 0, size * SS - 1, size * SS - 1], fill=fill)
    return img.resize((size, size), Image.Resampling.LANCZOS)
