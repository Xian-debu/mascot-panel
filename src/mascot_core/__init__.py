"""纯逻辑层：无 Win32 / 无 webview / 可在任何平台单测。"""

from mascot_core.geometry import PANEL_SIZE, Rect, Screen, ball_pos, clamp_rect, follow_rect
from mascot_core.hit import HitKind, HitRegion, hit_test
from mascot_core.state import Event, State, Transition, transition

__all__ = [
    "PANEL_SIZE", "Rect", "Screen", "ball_pos", "clamp_rect", "follow_rect",
    "HitKind", "HitRegion", "hit_test",
    "Event", "State", "Transition", "transition",
]
