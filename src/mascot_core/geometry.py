"""几何：跟随框位置、环绕球轨道、屏幕边界收敛。

全部使用**物理像素**（见 mascot-admin/docs/08 R-03）。本模块不认任何平台对象。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PANEL_SIZE = (340, 460)


@dataclass(frozen=True, slots=True)
class Rect:
    """左闭右开的整数矩形。x,y 是左上角，w,h 是宽高。"""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom

    def intersects(self, other: Rect) -> bool:
        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.bottom <= other.y
            or other.bottom <= self.y
        )

    def intersection_area(self, other: Rect) -> int:
        if not self.intersects(other):
            return 0
        w = min(self.right, other.right) - max(self.x, other.x)
        h = min(self.bottom, other.bottom) - max(self.y, other.y)
        return w * h

    def moved_to(self, x: int, y: int) -> Rect:
        return Rect(x, y, self.w, self.h)


@dataclass(frozen=True, slots=True)
class Screen:
    """一块显示器的可用工作区（物理像素）。"""

    width: int
    height: int
    x: int = 0
    y: int = 0

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)


def clamp_rect(rect: Rect, screen: Screen) -> Rect:
    """把矩形收进屏幕；屏幕比窗口还小时贴左上角（不产生负坐标）。"""
    max_x = max(screen.x, screen.x + screen.width - rect.w)
    max_y = max(screen.y, screen.y + screen.height - rect.h)
    x = min(max(rect.x, screen.x), max_x)
    y = min(max(rect.y, screen.y), max_y)
    return rect.moved_to(x, y)


def follow_rect(
    pet: Rect | None,
    offset: tuple[int, int],
    size: tuple[int, int] = PANEL_SIZE,
    screen: Screen | None = None,
) -> Rect | None:
    """跟随框相对宠物窗口的位置；宠物不存在时返回 None（调用方进入 idle）。"""
    if pet is None:
        return None
    r = Rect(pet.x + offset[0], pet.y + offset[1], size[0], size[1])
    return clamp_rect(r, screen) if screen is not None else r


def orbit_radius(pet: Rect, ratio: float, gap: int) -> float:
    """公转半径：以宠物窗口宽度的比例为基准，避免不同皮肤大小不一致。"""
    return pet.w * ratio + gap


def ball_pos(
    angle: float,
    pet: Rect,
    ratio: float = 0.34,
    gap: int = 10,
    ball_size: int = 0,
) -> tuple[int, int]:
    """给定角度（弧度）求球左上角坐标（物理像素，整数）。

    ball_size 用于把球心放到轨道上再回推左上角；传 0 表示直接返回轨道点。
    """
    cx, cy = pet.center
    r = orbit_radius(pet, ratio, gap)
    px = cx + r * math.cos(angle)
    py = cy + r * math.sin(angle)
    half = ball_size / 2
    return (round(px - half), round(py - half))


def angle_for_time(t: float, period_s: float, speed: float = 1.0) -> float:
    """时间 → 角度。period_s 是整整一圈的秒数；speed 由拖拽调速写入。"""
    if period_s <= 0:
        raise ValueError("period_s must be > 0")
    return (2 * math.pi * t * speed) / period_s

@dataclass(frozen=True, slots=True)
class OrbitLayout:
    """环绕态几何：球半径、轨道半径、整帧窗口边长（都是物理像素）。"""

    ball_r: int
    orbit_r: int
    window: int


def orbit_layout(
    pet: Rect, ball_ratio: float = 0.34, gap: int = 10, pad: int = 6
) -> OrbitLayout:
    """原版公式：球半径按宠物宽度比例，轨道要让球完全绕在宠物外圈。

    window 是正方形整帧窗口边长：轨道直径 + 两侧球 + 一点余量，
    这样彗尾和球都能画进同一张 UpdateLayeredWindow 里。
    """
    ball_r = max(30, int(pet.w * ball_ratio))
    orbit_r = max(150, pet.w // 2 + ball_r + gap)
    window = 2 * (orbit_r + ball_r + pad)
    return OrbitLayout(ball_r=ball_r, orbit_r=orbit_r, window=window)
