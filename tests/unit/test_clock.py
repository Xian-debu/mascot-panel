"""像素时钟球的纯逻辑测试：角度换算 + 确定性渲染 + 边界。"""

from __future__ import annotations

import math
import time

from PIL import Image

from mascot_render.clock import clock_angles, render_clock, render_orbit_frame

NOON = time.struct_time((2026, 10, 22, 12, 0, 0, 3, 295, -1))
THREE = time.struct_time((2026, 10, 22, 15, 0, 0, 3, 295, -1))
TEN_TEN = time.struct_time((2026, 10, 22, 10, 10, 0, 3, 295, -1))


def test_hour_angle_points_up_at_noon() -> None:
    hour, minute, _second = clock_angles(12, 0, 0)
    assert math.isclose(hour, -math.pi / 2, abs_tol=1e-9)
    assert math.isclose(minute, -math.pi / 2, abs_tol=1e-9)


def test_hour_angle_points_right_at_three() -> None:
    hour, _, _ = clock_angles(15, 0, 0)
    assert math.isclose(hour, 0.0, abs_tol=1e-9)


def test_minute_angle_at_quarter_past() -> None:
    _, minute, _ = clock_angles(10, 15, 0)
    assert math.isclose(minute, 0.0, abs_tol=1e-9)


def test_second_angle_tracks_seconds() -> None:
    _, _, sec = clock_angles(10, 10, 15)
    assert math.isclose(sec, 0.0, abs_tol=1e-9)


def test_render_clock_shape_and_alpha() -> None:
    img = render_clock(96, now=TEN_TEN)
    assert img.size == (96, 96)
    assert img.mode == "RGBA"
    alpha = img.getchannel("A")
    assert alpha.getextrema()[1] == 255
    assert alpha.getextrema()[0] == 0
    # 硬 alpha：只允许 0/255（像素语言，无抗锯齿）
    assert set(alpha.getdata()) <= {0, 255}


def test_render_clock_is_deterministic() -> None:
    a = render_clock(96, now=TEN_TEN, now_ts=0.0)
    b = render_clock(96, now=TEN_TEN, now_ts=0.0)
    assert list(a.getdata()) == list(b.getdata())


def test_render_clock_differs_by_time() -> None:
    a = render_clock(96, now=NOON)
    b = render_clock(96, now=THREE)
    assert a.tobytes() != b.tobytes()


def test_render_clock_stuck_uses_amber() -> None:
    normal = render_clock(96, now=TEN_TEN)
    stuck = render_clock(96, now=TEN_TEN, stuck=True)
    assert normal.tobytes() != stuck.tobytes()
    colors = {c for c in zip(stuck.tobytes()[0::4], stuck.tobytes()[1::4], stuck.tobytes()[2::4], strict=True)}
    assert any(r > 150 and g > 100 and b < 120 for r, g, b in colors)


def test_render_clock_rejects_tiny_size() -> None:
    try:
        render_clock(8, now=TEN_TEN)
    except ValueError as exc:
        assert "size" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_orbit_frame_has_tail_pixels() -> None:
    img = render_orbit_frame(
        300, ball_r=40, orbit_r=110, angle_deg=0.0, now=TEN_TEN, now_ts=0.0
    )
    assert img.size == (300, 300)
    assert img.getchannel("A").getbbox() is not None
    # 尾迹在球的后方（角度负方向）应存在像素：0° 时尾迹在右上 35° 处
    import math

    tx = 150 + round(110 * math.cos(math.radians(-35)))
    ty = 150 + round(110 * math.sin(math.radians(-35)))
    assert img.getpixel((tx, ty))[3] > 0


def test_orbit_frame_is_rgba() -> None:
    img = render_orbit_frame(200, ball_r=32, orbit_r=70, angle_deg=90.0, now=TEN_TEN)
    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"


def _opaque(im: Image.Image) -> int:
    return sum(1 for a in im.getchannel("A").getdata() if a)


def test_alert_ring_adds_pixels_outside_ball() -> None:
    plain = render_clock(96, now=TEN_TEN, now_ts=0.0)
    alert = render_clock(96, now=TEN_TEN, now_ts=0.0, alert=True)
    assert _opaque(alert) > _opaque(plain) + 40
    # 提示环在球外圈：外接矩形比平时更靠边
    plain_box = plain.getchannel("A").getbbox()
    alert_box = alert.getchannel("A").getbbox()
    assert plain_box is not None and alert_box is not None
    assert alert_box[0] <= plain_box[0] - 1 and alert_box[2] >= plain_box[2] + 1


def test_alert_ring_is_deterministic() -> None:
    a = render_clock(96, now=TEN_TEN, now_ts=0.0, alert=True)
    b = render_clock(96, now=TEN_TEN, now_ts=0.0, alert=True)
    assert list(a.getdata()) == list(b.getdata())


def test_orbit_frame_alert_adds_ring_around_ball() -> None:
    plain = render_orbit_frame(
        300, ball_r=40, orbit_r=110, angle_deg=0.0, now=TEN_TEN, now_ts=0.0
    )
    alert = render_orbit_frame(
        300, ball_r=40, orbit_r=110, angle_deg=0.0, now=TEN_TEN, now_ts=0.0, alert=True
    )
    assert _opaque(alert) > _opaque(plain) + 40
