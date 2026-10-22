"""状态机：替代旧实现里"靠 Popen/poll 判断窗口在不在"的做法。

五个状态：idle / idle_open / tracking / orbital / degraded。

idle_open = 宠物不在时用户手动展开的面板（右下角常驻），
这样"游戏没开"也能聊天，而不是进程在跑却什么都看不见。
每次转移带一个 reason 码，写日志后能被 `mascot doctor` 与用户报告解读。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    IDLE = "idle"
    IDLE_OPEN = "idle_open"
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

    # 降级只是"后端发不出消息"，不该吞掉用户交互：这些事件按降级前的状态继续生效，
    # 状态机本身留在 DEGRADED（横幅、重试逻辑都不变）。
    _DEGRADED_PASSTHROUGH = frozenset(
        {Event.PET_FOUND, Event.PET_LOST, Event.CLICK_CLOCK, Event.CLICK_BALL}
    )

    def push(self, event: Event) -> Transition:
        """推进一次，返回转移结果（副作用由调用方执行）。"""
        if event is Event.PROVIDER_DOWN and self.state is not State.DEGRADED:
            self.resume_state = self.state
        if self.state is State.DEGRADED and event in self._DEGRADED_PASSTHROUGH:
            base = self.resume_state or State.IDLE
            inner = transition(base, event)
            if inner.reason.startswith("IGNORED"):
                return Transition(State.DEGRADED, f"IGNORED:{event.name}")
            self.resume_state = inner.state
            return Transition(State.DEGRADED, f"DEGRADED:{inner.reason}", inner.effects)
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
        if state in (State.IDLE, State.IDLE_OPEN):
            # 待机态右下角有常驻小球；宠物出现后收球、面板改为跟随
            return Transition(State.TRACKING, "PET_FOUND", (SHOW_PANEL, HIDE_BALL))
        return Transition(state, "IGNORED:PET_FOUND")

    if event is Event.PET_LOST:
        if state is State.TRACKING:
            # 面板收起，回到待机：右下角常驻小球，仍可点开
            return Transition(State.IDLE, "PET_LOST", (HIDE_PANEL, SHOW_BALL))
        if state is State.ORBITAL:
            # 宠物消失时球没有轨道可绕：停帧并把球钉到右下角
            return Transition(State.IDLE, "PET_LOST", (STOP_FRAMES,))
        return Transition(state, "IGNORED:PET_LOST")

    if event is Event.CLICK_CLOCK:
        if state is State.TRACKING:
            return Transition(State.ORBITAL, "CLICK_CLOCK", (HIDE_PANEL, SHOW_BALL, START_FRAMES))
        if state is State.IDLE_OPEN:
            # 待机面板收进右下角小球
            return Transition(State.IDLE, "CLICK_CLOCK", (HIDE_PANEL, SHOW_BALL))
        return Transition(state, "IGNORED:CLICK_CLOCK")

    if event is Event.CLICK_BALL:
        if state is State.ORBITAL:
            return Transition(State.TRACKING, "CLICK_BALL", (STOP_FRAMES, HIDE_BALL, SHOW_PANEL))
        if state is State.IDLE:
            # 待机态点球 = 打开面板（钉在右下角，不跟随）
            return Transition(State.IDLE_OPEN, "CLICK_BALL", (SHOW_PANEL, HIDE_BALL))
        return Transition(state, "IGNORED:CLICK_BALL")

    if event is Event.PROVIDER_DOWN:
        if state is State.DEGRADED:
            return Transition(State.DEGRADED, "IGNORED:PROVIDER_DOWN")
        return Transition(State.DEGRADED, "PROVIDER_DOWN", (MARK_DEGRADED,))

    if event is Event.PROVIDER_READY:
        if state is State.DEGRADED:
            back = (
                State(resume_state)
                if resume_state in (State.TRACKING, State.ORBITAL, State.IDLE_OPEN)
                else State.IDLE
            )
            return Transition(back, "PROVIDER_READY", (CLEAR_DEGRADED,))
        return Transition(state, "IGNORED:PROVIDER_READY")

    if event is Event.RENDER_FAILED:
        if state is State.ORBITAL:
            return Transition(State.ORBITAL, "RENDER_RESTART", (STOP_FRAMES, START_FRAMES))
        return Transition(state, "IGNORED:RENDER_FAILED")

    return Transition(state, f"IGNORED:{event}")
