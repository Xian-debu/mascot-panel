from __future__ import annotations

import re

import pytest

from mascot_core.tokens import COLORS, css_variables, hex_to_rgb, pixel_palette


def test_hex_to_rgb() -> None:
    assert hex_to_rgb("#56d4dd") == (0x56, 0xD4, 0xDD)
    with pytest.raises(ValueError):
        hex_to_rgb("#fff")


def test_css_variables_contain_every_color() -> None:
    css = css_variables()
    for name, value in COLORS.items():
        assert f"--{name}: {value};" in css
    assert css.startswith(":root {")


def test_pixel_palette_monotonic_brightness() -> None:
    pal = pixel_palette(5)
    assert len(pal.colors) == 5
    sums = [sum(c) for c in pal.colors]
    assert sums == sorted(sums)
    assert pal.accent == hex_to_rgb(COLORS["accent"])


def test_palette_level_clamped() -> None:
    pal = pixel_palette(3)
    assert pal.by_level(-5) == pal.by_level(0)
    assert pal.by_level(99) == pal.by_level(2)


def test_css_has_no_surrogates() -> None:
    css = css_variables()
    assert re.search(r"--accent: #[0-9a-f]{6};", css)
