from __future__ import annotations

import math

import pytest

from mascot_core.geometry import (
    Rect,
    Screen,
    angle_for_time,
    ball_pos,
    clamp_rect,
    follow_rect,
    orbit_radius,
)


def test_rect_basics() -> None:
    r = Rect(10, 20, 100, 50)
    assert r.right == 110
    assert r.bottom == 70
    assert r.contains(10, 20)
    assert not r.contains(110, 20)  # 右开
    assert r.center == (60.0, 45.0)


def test_intersection_area() -> None:
    a = Rect(0, 0, 10, 10)
    assert a.intersects(Rect(5, 5, 10, 10))
    assert a.intersection_area(Rect(5, 5, 10, 10)) == 25
    assert a.intersection_area(Rect(20, 20, 5, 5)) == 0


def test_follow_rect_uses_offset() -> None:
    pet = Rect(1000, 500, 200, 300)
    panel = follow_rect(pet, (210, -130))
    assert panel == Rect(1210, 370, 340, 460)


def test_follow_rect_none_when_no_pet() -> None:
    assert follow_rect(None, (210, -130)) is None


def test_follow_rect_clamped_into_screen() -> None:
    pet = Rect(2400, 1200, 200, 300)
    screen = Screen(2560, 1600)
    panel = follow_rect(pet, (210, -130), screen=screen)
    assert panel is not None
    assert panel.right <= 2560
    assert panel.bottom <= 1600


def test_clamp_keeps_negative_screen_origin() -> None:
    screen = Screen(1920, 1080, x=-1920, y=0)
    r = clamp_rect(Rect(-3000, 100, 340, 460), screen)
    assert r.x == -1920
    assert r.y == 100


def test_orbit_radius_is_relative_to_pet_width() -> None:
    assert orbit_radius(Rect(0, 0, 200, 200), 0.34, 10) == pytest.approx(78.0)


def test_ball_pos_at_right_of_orbit() -> None:
    pet = Rect(0, 0, 200, 200)
    x, y = ball_pos(0.0, pet, ratio=0.34, gap=10)
    assert x == pytest.approx(100 + 78)
    assert y == pytest.approx(100)


def test_ball_pos_with_ball_size_centers_it() -> None:
    pet = Rect(0, 0, 200, 200)
    x, y = ball_pos(0.0, pet, ratio=0.34, gap=10, ball_size=20)
    assert x == pytest.approx(178 - 10)
    assert y == pytest.approx(90)


def test_ball_pos_top_when_quarter_turn() -> None:
    pet = Rect(0, 0, 200, 200)
    _, y = ball_pos(math.pi / 2, pet, ratio=0.34, gap=10)
    assert y == pytest.approx(178)


def test_angle_for_time() -> None:
    assert angle_for_time(0, 12) == 0
    assert angle_for_time(12, 12) == pytest.approx(2 * math.pi)
    assert angle_for_time(6, 12, speed=2) == pytest.approx(2 * math.pi)
    with pytest.raises(ValueError):
        angle_for_time(1, 0)
