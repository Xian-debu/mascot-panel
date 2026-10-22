"""状态机：替代旧实现里"靠 Popen/poll 判断窗口在不在"的做法。

四个状态：idle / tracking / orbital / degraded。
每次转移带一个 reason 码，写日志后能被 `mascot doctor` 与用户报告解读。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    IDLE = "idle"
    TRACKING = "tracking"
    ORBITAL = "orbital"
    DEGRADED = "degraded"


class Event(StrEnum):
    PET_FOUND = "pet_found"
    PET_LOST = "pet_lost"
    CLICK_CLOCK = "click_clock"
    CLICK_BALL = "click_ball"
    PROVIDER_DOWN = "provider_down"
    PROVIDER_READY = "provider_ready"
    RENDER_FAILED = "render_failed"


# 副作用名：由 app 层翻译成真实的窗口/帧循环调用。core 只描述"该做什么"。
SHOW_PANEL = "show_panel"
HIDE_PANEL = "hide_panel"
SHOW_BALL = "show_ball"
HIDE_BALL = "hide_ball"
START_FRAMES = "start_frames"
STOP_FRAMES = "stop_frames"
MARK_DEGRADED = "mark_degraded"
CLEAR_DEGRADED = "clear_degraded"


@dataclass(frozen=True, slots=True)
class Transition:
    state: State
    reason: str
    effects: tuple[str, ...] = ()


@dataclass(slots=True)
class Machine:
    """有记忆的状态机：记住进入 degraded 之前的状态，以便恢复。"""

    state: State = State.IDLE
    resume_state: State | None = None

    def push(self, event: Event) -> Transition:
        """推进一次，返回转移结果（副作用由调用方执行）。"""
        if event is Event.PROVIDER_DOWN and self.state is not State.DEGRADED:
            self.resume_state = self.state
        result = transition(self.state, event, self.resume_state)
        self.state = result.state
        if self.state is not State.DEGRADED:
            self.resume_state = None
        return result


def transition(
    state: State,
    event: Event,
    resume_state: State | None = None,
) -> Transition:
    """纯函数版转移表（测试与文档的单一真源）。"""
    if event is Event.PET_FOUND:
        if state is State.IDLE:
            return Transition(State.TRACKING, "PET_FOUND", (SHOW_PANEL,))
        return Transition(state, "IGNORED:PET_FOUND")

    if event is Event.PET_LOST:
        if state is State.TRACKING:
            return Transition(State.IDLE, "PET_LOST", (HIDE_PANEL,))
        if state is State.ORBITAL:
            # 宠物消失时球没有轨道可绕，收起球回到 idle
            return Transition(State.IDLE, "PET_LOST", (STOP_FRAMES, HIDE_BALL))
        return Transition(state, "IGNORED:PET_LOST")

    if event is Event.CLICK_CLOCK:
        if state is State.TRACKING:
            return Transition(State.ORBITAL, "CLICK_CLOCK", (HIDE_PANEL, SHOW_BALL, START_FRAMES))
        return Transition(state, "IGNORED:CLICK_CLOCK")

    if event is Event.CLICK_BALL:
        if state is State.ORBITAL:
            return Transition(State.TRACKING, "CLICK_BALL", (STOP_FRAMES, HIDE_BALL, SHOW_PANEL))
        return Transition(state, "IGNORED:CLICK_BALL")

    if event is Event.PROVIDER_DOWN:
        if state is State.DEGRADED:
            return Transition(State.DEGRADED, "IGNORED:PROVIDER_DOWN")
        return Transition(State.DEGRADED, "PROVIDER_DOWN", (MARK_DEGRADED,))

    if event is Event.PROVIDER_READY:
        if state is State.DEGRADED:
            back = (
                State(resume_state)
                if resume_state in (State.TRACKING, State.ORBITAL)
                else State.IDLE
            )
            return Transition(back, "PROVIDER_READY", (CLEAR_DEGRADED,))
        return Transition(state, "IGNORED:PROVIDER_READY")

    if event is Event.RENDER_FAILED:
        if state is State.ORBITAL:
            return Transition(State.ORBITAL, "RENDER_RESTART", (STOP_FRAMES, START_FRAMES))
        return Transition(state, "IGNORED:RENDER_FAILED")

    return Transition(state, f"IGNORED:{event}")
