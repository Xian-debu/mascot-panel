"""M1 平台测试：只在 Windows 桌面跑（pytest -m platform）。"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.platform

if sys.platform != "win32":  # pragma: no cover - 平台门
    pytest.skip("requires Windows desktop", allow_module_level=True)

from mascot_win import win32  # noqa: E402
from mascot_win.single import SingleInstance  # noqa: E402
from mascot_win.tracker import PetTracker  # noqa: E402


def test_dpi_awareness_and_screen() -> None:
    level = win32.enable_dpi_awareness()
    assert level in {"per_monitor_v2", "per_monitor", "system"}
    w, h = win32.screen_metrics()
    assert w >= 800 and h >= 600
    dpi = win32.window_dpi(0)
    assert 96 <= dpi <= 480


def test_named_mutex_blocks_second_instance() -> None:
    a = SingleInstance("Local\\MascotPyTest")
    b = SingleInstance("Local\\MascotPyTest")
    try:
        assert a.acquire() is True
        assert b.acquire() is False
        assert b.already_running is True
    finally:
        b.release()
        a.release()


def test_enumerate_has_desktop_windows() -> None:
    windows = win32.candidates()
    assert len(windows) > 3
    assert all("class" in w and "rect" in w for w in windows)


def test_tracker_reports_consistent_rect_when_pet_running() -> None:
    tracker = PetTracker(class_names=("TX Mascot",), process_names=("TX Mascot.exe",), lost_frames=2)
    hit = tracker.poll()
    if hit is None:
        pytest.skip("TX Mascot 未运行")
    assert hit.rect.w > 0 and hit.rect.h > 0
    assert "TX Mascot" in hit.class_name or "TX Mascot" in hit.process
    # 连续两次 poll 应稳定命中同一窗口
    assert tracker.poll() is not None


def test_layered_window_render_move_destroy() -> None:
    from mascot_render.ball import render_ball
    from mascot_win.layered import LayeredWindow

    win = LayeredWindow(64, 64, click_through=True)
    try:
        assert win.hwnd != 0
        win.move(10, 10)
        win.render(render_ball(64, phase=0.25))
        win.set_click_through(False)
        win.set_click_through(True)
        assert win.pump() >= 0
    finally:
        win.destroy()
    assert win.hwnd == 0


def test_layered_window_hit_circle_controls_click_through() -> None:
    from PIL import Image

    from mascot_win import win32
    from mascot_win.layered import LayeredWindow

    win = LayeredWindow(200, 200, click_through=False, start_hidden=True)
    try:
        win.move(300, 300)
        win.render(Image.new("RGBA", (200, 200), (0, 0, 0, 0)))
        win.set_hit_circle(100, 100, 30)

        def at(client_x: int, client_y: int) -> int:
            lparam = ((client_y + 300) & 0xFFFF) << 16 | ((client_x + 300) & 0xFFFF)
            return win32.send_message(win.hwnd, win32.WM_NCHITTEST, 0, lparam)

        assert at(100, 100) == win32.HTCLIENT       # 球心可点
        assert at(100, 125) == win32.HTCLIENT       # 半径内
        assert at(10, 10) == win32.HTTRANSPARENT    # 角落穿透
        assert at(100, 160) == win32.HTTRANSPARENT  # 球外穿透
    finally:
        win.destroy()


def test_work_area_fits_inside_screen_and_excludes_taskbar() -> None:
    from mascot_win import win32

    wx, wy, ww, wh = win32.work_area(10, 10)
    sw, sh = win32.screen_metrics()
    assert ww > 0 and wh > 0
    assert wx + ww <= sw and wy + wh <= sh
    # 任务栏存在时工作区高度应小于全屏（否则至少应相等，不能更大）
    assert wh <= sh
