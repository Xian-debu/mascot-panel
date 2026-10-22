"""像素时钟球：移植原版 orbital_render.py 的像素语言（v11 版）。

为什么不用渐变球：原版用户反馈"太重度马赛克/看不到有效信息"之后收敛出的
44 格像素球才是这个 IP 的视觉基线 —— 硬色阶、NEAREST 放大、0/255 alpha、
无抗锯齿。新版第一版用了渐变球，效果明显不如原版（2026-10-22 用户反馈）。

纯 PIL，不碰 Win32，时间由调用方注入，所以能在 Linux 上做确定性快照。
"""

from __future__ import annotations

import math
import time

from PIL import Image, ImageDraw

from mascot_core.tokens import PIXEL, PIXEL_AMBER, hex_to_rgb

RGB = tuple[int, int, int]

# 视觉参数（与旧版一致：球占窗口 42%，44 格，2 格发光，3 段球体）
BALL_RATIO = 0.42
CELLS_ACROSS = 22
GLOW_CELLS = 2
TAIL_DEG = 65
TAIL_STEP_DEG = 2.5


def _rgb(name: str, palette: dict[str, str]) -> RGB:
    return hex_to_rgb(palette[name])


def palette_for(stuck: bool) -> dict[str, str]:
    """正常=青色家族；降级=琥珀家族（状态语义与面板状态灯一致）。"""
    return PIXEL_AMBER if stuck else PIXEL


def clock_angles(
    hour: int, minute: int, second: float
) -> tuple[float, float, float]:
    """三个指针的角度（弧度，0 = 12 点方向，顺时针；屏幕 y 向下）。"""
    hour_angle = (hour % 12 * 30 + minute * 0.5 + second / 120.0) * math.pi / 180 - math.pi / 2
    min_angle = (minute * 6 + second * 0.1) * math.pi / 180 - math.pi / 2
    sec_angle = (second * 6) * math.pi / 180 - math.pi / 2
    return hour_angle, min_angle, sec_angle


def _draw_alert_ring(
    img: Image.Image, cx: int, cy: int, r: float, palette: dict[str, str]
) -> None:
    """新消息提示环（M30）：28 个像素点围一圈亮环，硬边不抗锯齿。"""
    dr = ImageDraw.Draw(img)
    color = (*_rgb("cyan-bright", palette), 255)
    for i in range(28):
        a = 2 * math.pi * i / 28
        x = round(cx + r * math.cos(a))
        y = round(cy + r * math.sin(a))
        dr.rectangle([x - 1, y - 1, x + 1, y + 1], fill=color)


def _draw_sparkle(
    dr: ImageDraw.ImageDraw, x: int, y: int, big: bool, color: RGB, pulse: float
) -> None:
    """像素十字星光：大星带射线，小星是 2x2 点 + 四向短线。"""
    if big:
        dr.rectangle([x - 1, y - 1, x + 1, y + 1], fill=(*color, 255))
        ray = 2 if pulse > 0.75 else 1
        for s in range(1, ray + 1):
            dr.rectangle([x - 2 - s, y, x - 2 - s, y], fill=(*color, 150))
            dr.rectangle([x + 2 + s, y, x + 2 + s, y], fill=(*color, 150))
            dr.rectangle([x, y - 2 - s, x, y - 2 - s], fill=(*color, 150))
            dr.rectangle([x, y + 2 + s, x, y + 2 + s], fill=(*color, 150))
    else:
        dr.rectangle([x, y, x + 1, y + 1], fill=(*color, 255))
        dr.rectangle([x - 2, y, x - 2, y], fill=(*color, 140))
        dr.rectangle([x + 3, y, x + 3, y], fill=(*color, 140))
        dr.rectangle([x, y - 2, x, y - 2], fill=(*color, 140))
        dr.rectangle([x, y + 3, x, y + 3], fill=(*color, 140))


def _render_sprite(
    size: int,
    *,
    now: time.struct_time,
    stuck: bool,
    hover: bool,
    pulse: float,
) -> Image.Image:
    """在低分辨率网格上画球，再 NEAREST 放大 —— 像素语言的核心。"""
    pal = palette_for(stuck)
    p_edge = _rgb("edge", pal)
    p_mid = _rgb("mid", pal)
    p_hi = _rgb("hi", pal)
    p_core = _rgb("core", pal)
    p_cyan = _rgb("cyan", pal)
    p_bright = _rgb("cyan-bright", pal)
    p_white = _rgb("white", pal)
    p_navy = _rgb("navy", pal)

    ball_r = max(8, round(size * BALL_RATIO))
    cell = max(2, round(ball_r / CELLS_ACROSS))
    ball_cells = round(ball_r / cell)
    g = (ball_cells + GLOW_CELLS) * 2
    c = g // 2
    img = Image.new("RGBA", (g, g), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)

    # 阶梯实色发光（像素规则：用色阶，不用 alpha 光晕）
    arm2 = ball_cells + 2
    glow_outer = (p_bright if hover else p_cyan)
    dr.rectangle([c - arm2, c - 1, c + arm2, c + 1], fill=(*p_edge, 255))
    dr.rectangle([c - 1, c - arm2, c + 1, c + arm2], fill=(*p_edge, 255))
    arm1 = ball_cells + 1
    dr.rectangle([c - arm1, c - 1, c + arm1, c + 1], fill=(*glow_outer, 160))
    dr.rectangle([c - 1, c - arm1, c + 1, c + arm1], fill=(*glow_outer, 160))

    # 球体：三段实色带，向光偏移，读起来像球而不是同心圆
    r = ball_cells
    dr.ellipse([c - r, c - r, c + r, c + r], fill=(*p_edge, 255))
    if r - 3 > 0:
        dr.ellipse(
            [c - 1 - (r - 3), c - 1 - (r - 3), c - 1 + (r - 3), c - 1 + (r - 3)],
            fill=(*p_mid, 255),
        )
    if r >= 8:
        dr.ellipse(
            [c - 2 - (r - 6), c - 3 - (r - 6), c - 2 + (r - 6), c - 3 + (r - 6)],
            fill=(*p_hi, 255),
        )
    if r >= 12:
        dr.ellipse(
            [c - 3 - (r - 10), c - 4 - (r - 10), c - 3 + (r - 10), c - 4 + (r - 10)],
            fill=(*p_core, 255),
        )

    # 月牙高光 + 底部台阶反光
    hx, hy = c - r + 4, c - r + 4
    dr.rectangle([hx, hy, hx + 2, hy + 1], fill=(*p_white, 255))
    dr.rectangle([hx - 1, hy + 1, hx, hy + 2], fill=(*p_white, 170))
    for dx, dy in ((-7, 9), (-2, 10), (3, 10), (7, 9)):
        dr.rectangle([c + dx, c + dy, c + dx + 1, c + dy], fill=(*p_bright, 210))

    # 1 格描边 + 深色表盘
    dr.ellipse(
        [c - r, c - r, c + r, c + r],
        outline=(*p_bright, 255) if hover else (*p_cyan, 255),
        width=1,
    )
    dr.ellipse(
        [c - (r - 3), c - (r - 3), c + (r - 3), c + (r - 3)],
        fill=(*p_navy, 255),
    )

    hour_angle, min_angle, sec_angle = clock_angles(now.tm_hour, now.tm_min, now.tm_sec)
    hour_tick = round(now.tm_hour % 12 * 5 + now.tm_min / 12 ) % 12
    min_tick = round(now.tm_min / 5) % 12
    tick_r = r - 2

    # 12 个刻度：3 的倍数是短线，其余是单像素点
    for i in range(12):
        a = (i * 30 - 90) * math.pi / 180
        tx = round(c + tick_r * math.cos(a))
        ty = round(c + tick_r * math.sin(a))
        if i % 3 == 0:
            x0 = round(c + (r - 4) * math.cos(a))
            y0 = round(c + (r - 4) * math.sin(a))
            dr.line([x0, y0, tx, ty], fill=(*p_cyan, 240), width=1)
        else:
            dr.rectangle([tx, ty, tx, ty], fill=(*p_cyan, 170))

    # 时分位置各一颗星光，秒针靠近刻度时点亮
    for i in range(12):
        a = (i * 30 - 90) * math.pi / 180
        tx = round(c + tick_r * math.cos(a))
        ty = round(c + tick_r * math.sin(a))
        if i == hour_tick:
            _draw_sparkle(dr, tx, ty, True, p_bright, pulse)
        elif i == min_tick:
            _draw_sparkle(dr, tx, ty, False, p_white, pulse)

    # 指针：时=短粗、分=中、秒=细长
    len_h = max(5, round(ball_cells * 0.42))
    len_m = max(7, round(ball_cells * 0.62))
    len_s = max(9, round(ball_cells * 0.78))
    dr.line(
        [c, c, round(c + len_h * math.cos(hour_angle)), round(c + len_h * math.sin(hour_angle))],
        fill=(*p_cyan, 255),
        width=3,
    )
    dr.line(
        [c, c, round(c + len_m * math.cos(min_angle)), round(c + len_m * math.sin(min_angle))],
        fill=(*p_cyan, 255),
        width=2,
    )
    dr.line(
        [
            round(c - 3 * math.cos(sec_angle)),
            round(c - 3 * math.sin(sec_angle)),
            round(c + len_s * math.cos(sec_angle)),
            round(c + len_s * math.sin(sec_angle)),
        ],
        fill=(*p_cyan, 255),
        width=1,
    )

    # 中心轴
    dr.rectangle([c - 1, c - 1, c + 1, c + 1], fill=(*p_navy, 255))
    dr.rectangle([c, c, c, c], fill=(*p_bright, 255))

    # 硬 alpha 快照 + NEAREST 放大（无 AA、无软边）
    def snap(v: int) -> int:
        return 0 if v < 128 else 255

    alpha = img.getchannel("A").point(snap)
    img.putalpha(alpha)
    return img.resize((g * cell, g * cell), Image.Resampling.NEAREST)


def render_clock(
    size: int = 96,
    *,
    now: time.struct_time | None = None,
    now_ts: float | None = None,
    stuck: bool = False,
    hover: bool = False,
    alert: bool = False,
) -> Image.Image:
    """画一颗像素时钟球（返回 size×size 的 RGBA，球居中，四周透明）。"""
    if size < 16:
        raise ValueError("size too small")
    if now is None:
        now = time.localtime(now_ts)
    pulse = 0.5 + 0.5 * math.sin((now_ts if now_ts is not None else time.time()) / 0.573)
    sprite = _render_sprite(size, now=now, stuck=stuck, hover=hover, pulse=pulse)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(sprite, ((size - sprite.width) // 2, (size - sprite.height) // 2))
    if alert:
        # M30 状态灯：新消息到达时在球外圈亮一圈像素，2.5s 后自动消失
        _draw_alert_ring(canvas, size // 2, size // 2, max(6.0, size / 2 - 4), palette_for(stuck))
    return canvas


def render_orbit_frame(
    size: int,
    *,
    ball_r: int,
    orbit_r: float,
    angle_deg: float,
    now: time.struct_time | None = None,
    now_ts: float | None = None,
    stuck: bool = False,
    hover: bool = False,
    alert: bool = False,
    tail_deg: float = TAIL_DEG,
) -> Image.Image:
    """整帧：像素彗尾 + 球（球心按 angle_deg 落在 orbit_r 上）。供后续环绕态使用。"""
    if now is None:
        now = time.localtime(now_ts)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    cx = cy = size // 2
    pal = palette_for(stuck)
    p_cyan = _rgb("cyan", pal)
    p_bright = _rgb("cyan-bright", pal)

    n = max(2, int(tail_deg / TAIL_STEP_DEG))
    for i in range(n):
        a0 = angle_deg - (i + 1) * TAIL_STEP_DEG
        t = i / (n - 1)
        rad = math.radians(a0)
        x = cx + orbit_r * math.cos(rad)
        y = cy + orbit_r * math.sin(rad)
        s = max(1, int(ball_r * (0.14 - 0.11 * t)))
        alpha = int(130 * (1 - t) ** 1.5)
        if alpha <= 0:
            continue
        dr.rectangle([x - s, y - s, x + s, y + s], fill=(*p_cyan, alpha))
    head = math.radians(angle_deg - TAIL_STEP_DEG)
    hx = cx + orbit_r * math.cos(head)
    hy = cy + orbit_r * math.sin(head)
    dr.rectangle([hx - 2, hy, hx + 2, hy], fill=(*p_bright, 170))
    dr.rectangle([hx, hy - 2, hx, hy + 2], fill=(*p_bright, 170))

    sprite = _render_sprite(ball_r * 2, now=now, stuck=stuck, hover=hover, pulse=0.5)
    rad = math.radians(angle_deg)
    bx = cx + orbit_r * math.cos(rad)
    by = cy + orbit_r * math.sin(rad)
    img.alpha_composite(sprite, (round(bx - sprite.width / 2), round(by - sprite.height / 2)))
    if alert:
        _draw_alert_ring(img, round(bx), round(by), ball_r + 8, pal)
    return img
