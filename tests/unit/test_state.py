from __future__ import annotations

from mascot_core.state import (
    HIDE_BALL,
    HIDE_PANEL,
    SHOW_BALL,
    SHOW_PANEL,
    START_FRAMES,
    STOP_FRAMES,
    Event,
    Machine,
    State,
    transition,
)


def test_idle_to_tracking_on_pet_found() -> None:
    t = transition(State.IDLE, Event.PET_FOUND)
    assert t.state is State.TRACKING
    assert SHOW_PANEL in t.effects
    assert t.reason == "PET_FOUND"


def test_click_clock_switches_to_orbital() -> None:
    t = transition(State.TRACKING, Event.CLICK_CLOCK)
    assert t.state is State.ORBITAL
    assert set(t.effects) == {HIDE_PANEL, SHOW_BALL, START_FRAMES}


def test_click_ball_returns_to_tracking() -> None:
    t = transition(State.ORBITAL, Event.CLICK_BALL)
    assert t.state is State.TRACKING
    assert set(t.effects) == {STOP_FRAMES, HIDE_BALL, SHOW_PANEL}


def test_ignored_event_keeps_state() -> None:
    t = transition(State.IDLE, Event.CLICK_CLOCK)
    assert t.state is State.IDLE
    assert t.effects == ()
    assert t.reason.startswith("IGNORED:")


def test_degraded_remembers_and_restores_orbital() -> None:
    m = Machine(state=State.ORBITAL)
    t = m.push(Event.PROVIDER_DOWN)
    assert t.state is State.DEGRADED
    assert m.resume_state is State.ORBITAL
    t2 = m.push(Event.PROVIDER_READY)
    assert t2.state is State.ORBITAL
    assert m.resume_state is None


def test_degraded_restores_idle() -> None:
    m = Machine(state=State.IDLE)
    m.push(Event.PROVIDER_DOWN)
    assert m.push(Event.PROVIDER_READY).state is State.IDLE


def test_repeated_provider_down_is_ignored() -> None:
    m = Machine(state=State.TRACKING)
    m.push(Event.PROVIDER_DOWN)
    t = m.push(Event.PROVIDER_DOWN)
    assert t.state is State.DEGRADED
    assert t.reason == "IGNORED:PROVIDER_DOWN"


def test_pet_lost_in_orbital_keeps_ball_visible() -> None:
    # M13：宠物消失后球不再收掉，而是钉到右下角继续可点
    t = transition(State.ORBITAL, Event.PET_LOST)
    assert t.state is State.IDLE
    assert STOP_FRAMES in t.effects
    assert HIDE_BALL not in t.effects


def test_idle_click_ball_opens_standalone_panel() -> None:
    t = transition(State.IDLE, Event.CLICK_BALL)
    assert t.state is State.IDLE_OPEN
    assert set(t.effects) == {SHOW_PANEL, HIDE_BALL}


def test_idle_open_click_clock_collapses_to_ball() -> None:
    t = transition(State.IDLE_OPEN, Event.CLICK_CLOCK)
    assert t.state is State.IDLE
    assert set(t.effects) == {HIDE_PANEL, SHOW_BALL}


def test_pet_found_from_idle_open_keeps_panel_and_hides_ball() -> None:
    t = transition(State.IDLE_OPEN, Event.PET_FOUND)
    assert t.state is State.TRACKING
    assert set(t.effects) == {SHOW_PANEL, HIDE_BALL}


def test_pet_lost_from_tracking_returns_to_standalone_ball() -> None:
    t = transition(State.TRACKING, Event.PET_LOST)
    assert t.state is State.IDLE
    assert set(t.effects) == {HIDE_PANEL, SHOW_BALL}


def test_idle_open_is_restored_after_degraded() -> None:
    m = Machine(state=State.IDLE_OPEN)
    m.push(Event.PROVIDER_DOWN)
    assert m.push(Event.PROVIDER_READY).state is State.IDLE_OPEN


def test_render_failed_restarts_orbital() -> None:
    t = transition(State.ORBITAL, Event.RENDER_FAILED)
    assert t.state is State.ORBITAL
    assert t.reason == "RENDER_RESTART"


def test_degraded_still_allows_click_clock() -> None:
    # A1：降级不吞交互 —— 环绕球状态下点时钟照样回面板，但状态仍是 DEGRADED
    m = Machine(state=State.ORBITAL)
    m.push(Event.PROVIDER_DOWN)
    t = m.push(Event.CLICK_CLOCK)
    assert t.state is State.DEGRADED
    assert t.reason == "IGNORED:CLICK_CLOCK"
    assert t.effects == ()
    assert m.resume_state is State.ORBITAL


def test_degraded_passthrough_from_tracking_click_clock() -> None:
    m = Machine(state=State.TRACKING)
    m.push(Event.PROVIDER_DOWN)
    t = m.push(Event.CLICK_CLOCK)
    assert t.state is State.DEGRADED
    assert set(t.effects) == {HIDE_PANEL, SHOW_BALL, START_FRAMES}
    assert m.resume_state is State.ORBITAL
    assert m.push(Event.PROVIDER_READY).state is State.ORBITAL


def test_degraded_passthrough_click_ball_back_to_panel() -> None:
    m = Machine(state=State.ORBITAL)
    m.push(Event.PROVIDER_DOWN)
    t = m.push(Event.CLICK_BALL)
    assert t.state is State.DEGRADED
    assert set(t.effects) == {STOP_FRAMES, HIDE_BALL, SHOW_PANEL}
    assert m.resume_state is State.TRACKING


def test_degraded_passthrough_pet_found_keeps_follow_placement() -> None:
    m = Machine(state=State.IDLE)
    m.push(Event.PROVIDER_DOWN)
    t = m.push(Event.PET_FOUND)
    assert t.state is State.DEGRADED
    assert set(t.effects) == {SHOW_PANEL, HIDE_BALL}
    assert m.resume_state is State.TRACKING


def test_machine_is_pure_without_side_effects() -> None:
    m = Machine()
    assert m.state is State.IDLE
    assert m.resume_state is None
