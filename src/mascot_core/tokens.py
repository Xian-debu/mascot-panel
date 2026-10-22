"""设计令牌：一份真源，同时喂 WebView 的 CSS 变量和 PIL 的像素调色板。

旧实现的颜色散在 HTML、Python、截图工具里三处，改一个青色要改三个文件。
"""

from __future__ import annotations

from dataclasses import dataclass

# 16 进制颜色（不带 #），键名与 CSS 变量一一对应。
COLORS: dict[str, str] = {
    "bg": "#0e1116",
    "card": "#161b22",
    "border": "#2d333b",
    "text": "#e6edf3",
    "text-dim": "#8b949e",
    "text-muted": "#484f58",
    "accent": "#56d4dd",
    "amber": "#e3b341",
    "red": "#f85149",
    "green": "#3fb950",
}

FONTS: dict[str, str] = {
    "mono": '"Cascadia Mono", "Consolas", monospace',
    "sans": '"Segoe UI", "Microsoft YaHei UI", sans-serif',
}

SIZES: dict[str, int] = {"fs-11": 11, "fs-12": 12, "fs-13": 13, "fs-15": 15}
SPACING: dict[str, int] = {"s1": 4, "s2": 8, "s3": 12, "s4": 16}
RADIUS: dict[str, int] = {"r-card": 10, "r-panel": 14}
MOTION_MS: dict[str, int] = {"fast": 120, "base": 200}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"bad hex color: {value!r}")
    return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def css_variables() -> str:
    """生成 :root { --bg: ...; } 供 web/ 直接注入。"""
    lines = [f"  --{name}: {value};" for name, value in COLORS.items()]
    lines += [f"  --{name}: {value}px;" for name, value in SIZES.items()]
    lines += [f"  --{name}: {value}px;" for name, value in SPACING.items()]
    lines += [f"  --{name}: {value}px;" for name, value in RADIUS.items()]
    lines += [f"  --{name}: {value}ms;" for name, value in MOTION_MS.items()]
    lines += [f"  --{name}: {value};" for name, value in FONTS.items()]
    return ":root {\n" + "\n".join(lines) + "\n}"


@dataclass(frozen=True, slots=True)
class Palette:
    """像素球用的降采样调色板：球只有 4–5 阶，HTML 是连续色，但色相必须同源。"""

    colors: tuple[tuple[int, int, int], ...]
    accent: tuple[int, int, int]

    def by_level(self, level: int) -> tuple[int, int, int]:
        if not self.colors:
            raise ValueError("empty palette")
        return self.colors[max(0, min(level, len(self.colors) - 1))]


def pixel_palette(steps: int = 5) -> Palette:
    """把强调色按亮度分档，供球体着色；steps 与旧的 4 阶亮环对应。"""
    if steps < 2:
        raise ValueError("steps must be >= 2")
    r, g, b = hex_to_rgb(COLORS["accent"])
    shades = []
    for i in range(steps):
        # 从 0.35 到 1.0 线性提亮，避免最暗一阶接近黑色
        k = 0.35 + 0.65 * (i / (steps - 1))
        shades.append((round(r * k), round(g * k), round(b * k)))
    return Palette(tuple(shades), (r, g, b))
