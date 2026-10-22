"""待机球单击/双击判定（M25）。"""

import pytest

from mascot_core.click import DOUBLE, SINGLE, ClickGate


def test_first_click_is_pending() -> None:
    gate = ClickGate(350)
    assert gate.click(1000.0) is None
    assert gate.pending is True


def test_tick_inside_window_keeps_pending() -> None:
    gate = ClickGate(350)
    gate.click(1000.0)
    assert gate.tick(1200.0) is None
    assert gate.pending is True


def test_tick_after_window_emits_single() -> None:
    gate = ClickGate(350)
    gate.click(1000.0)
    assert gate.tick(1349.0) is None
    assert gate.tick(1351.0) == SINGLE
    assert gate.pending is False
    assert gate.tick(2000.0) is None


def test_second_click_inside_window_is_double() -> None:
    gate = ClickGate(350)
    assert gate.click(1000.0) is None
    assert gate.click(1080.0) == DOUBLE
    assert gate.pending is False
    assert gate.tick(1200.0) is None


def test_two_slow_clicks_are_two_singles() -> None:
    gate = ClickGate(350)
    gate.click(1000.0)
    assert gate.tick(1500.0) == SINGLE
    assert gate.click(1600.0) is None
    assert gate.tick(1900.0) is None
    assert gate.tick(2000.0) == SINGLE


def test_reset_drops_pending_click() -> None:
    gate = ClickGate(350)
    gate.click(1000.0)
    gate.reset()
    assert gate.pending is False
    assert gate.tick(2000.0) is None


def test_third_click_after_double_starts_new_pending() -> None:
    gate = ClickGate(350)
    gate.click(1000.0)
    assert gate.click(1050.0) == DOUBLE
    assert gate.click(3000.0) is None
    assert gate.pending is True


def test_negative_window_rejected() -> None:
    with pytest.raises(ValueError):
        ClickGate(-1)


def test_zero_window_disables_double_click() -> None:
    gate = ClickGate(0)
    # 关掉双击手势：每次点击立刻就是 single，不再挂起等待
    assert gate.click(1000.0) == SINGLE
    assert gate.pending is False
    assert gate.tick(1000.0) is None
    assert gate.click(1010.0) == SINGLE
