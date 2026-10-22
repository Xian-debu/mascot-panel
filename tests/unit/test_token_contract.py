"""设计令牌契约：Python token 与面板 HTML 必须同源，不许各写一份颜色。"""

from __future__ import annotations

import re

from mascot_app.runtime import TOKENS_PLACEHOLDER, load_panel_html
from mascot_core.tokens import ALPHA_VARS, COLORS, MOTION_MS, RADIUS, SIZES, SPACING, css_variables
from mascot_render.ball import BADGE_COLORS


def test_placeholder_is_replaced() -> None:
    html = load_panel_html()
    assert TOKENS_PLACEHOLDER not in html
    assert html.count(":root {") == 1


def test_every_declared_variable_is_defined() -> None:
    html = load_panel_html()
    used = set(re.findall(r"var\(--([a-z0-9-]+)\)", html))
    declared = set(COLORS) | set(ALPHA_VARS) | set(SIZES) | set(SPACING) | set(RADIUS) | set(MOTION_MS)
    missing = used - declared
    assert not missing, f"HTML 用了未声明的 token: {sorted(missing)}"


def test_no_hardcoded_hex_outside_tokens() -> None:
    html = load_panel_html()
    styles = html.split("<style>", 1)[1].split("</style>", 1)[0]
    rootless = styles.replace(css_variables(), "")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", rootless), "CSS 里还有写死的颜色"


def test_badge_colors_come_from_tokens() -> None:
    for state, (token, alpha) in BADGE_COLORS.items():
        assert token in COLORS, f"{state} 引用了不存在的 token {token}"
        assert 0 <= alpha <= 255
