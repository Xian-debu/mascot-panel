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
    "violet": "#a78bfa",
}

FONTS: dict[str, str] = {
    "mono": '"Cascadia Mono", "Consolas", monospace',
    "sans": '"Segoe UI", "Microsoft YaHei UI", sans-serif',
}

SIZES: dict[str, int] = {"fs-11": 11, "fs-12": 12, "fs-13": 13, "fs-15": 15}
SPACING: dict[str, int] = {"s1": 4, "s2": 8, "s3": 12, "s4": 16}
RADIUS: dict[str, int] = {"r-card": 10, "r-panel": 14}
MOTION_MS: dict[str, int] = {"fast": 120, "base": 200}

# 像素时钟球的硬色阶：像素语言需要明确的 5 个色阶，不能靠 alpha 渐变。
# 取自原版 orbital_render 的调色板（用户认可的视觉基线），state=降级时换琥珀家族。
PIXEL: dict[str, str] = {
    "edge": "#081a2e",
    "mid": "#165c7c",
    "hi": "#4096b2",
    "core": "#96e6f0",
    "cyan": "#00d4d4",
    "cyan-bright": "#00ebff",
    "white": "#ebfcff",
    "navy": "#061222",
}

PIXEL_AMBER: dict[str, str] = {
    "edge": "#2e1f08",
    "mid": "#7c5a16",
    "hi": "#b28a40",
    "core": "#f0e096",
    "cyan": "#d4a400",
    "cyan-bright": "#ffd000",
    "white": "#fffceb",
    "navy": "#221606",
}


# 出错时的提示环：与琥珀/青色同一套像素语言，只是换成红家族
PIXEL_RED: dict[str, str] = {
    "edge": "#2e0808",
    "mid": "#7c1616",
    "hi": "#b24040",
    "core": "#f09696",
    "cyan": "#d40000",
    "cyan-bright": "#ff4d4d",
    "white": "#ffe8e8",
    "navy": "#220606",
}


# 由主色派生出的半透明变体：CSS 里的描边/底色不再手写 rgba，改颜色只改 COLORS。
# 三套配色：深空是既有风格（默认），暖夜偏暖的暗色，浅色给白天用。
# 每套必须给全 11 个键——CSS 里所有颜色都从这里派生，缺一个就会掉回硬编码深色。
THEMES: dict[str, dict[str, str]] = {
    "space": COLORS,
    "warm": {
        "bg": "#14100c",
        "card": "#1f1813",
        "border": "#3a2d24",
        "text": "#f2e8dc",
        "text-dim": "#b09b88",
        "text-muted": "#6b5a4b",
        "accent": "#e8a04f",
        "amber": "#f0c060",
        "red": "#ff7b72",
        "green": "#7ee0a0",
        "violet": "#c9a2ff",
    },
    "light": {
        "bg": "#f6f8fa",
        "card": "#ffffff",
        "border": "#d0d7de",
        "text": "#1f2328",
        "text-dim": "#57606a",
        "text-muted": "#8c959f",
        "accent": "#0e8a9a",
        "amber": "#9a6700",
        "red": "#cf222e",
        "green": "#1a7f37",
        "violet": "#8250df",
    },
}

THEME_LABELS: dict[str, str] = {"space": "深空", "warm": "暖夜", "light": "浅色"}

# 面板里沿用旧别名（memos.css / messages.css / settings.css 早先写下的 --line、--card-solid…），
# 这里统一映射到正式 token，免得三套配色时旧别名掉回硬编码深色。
ALIAS_VARS: dict[str, str] = {
    "line": "border",
    "card-solid": "card",
    "panel": "card",
    "fg": "text",
    "muted": "text-dim",
}

ALPHA_VARS: dict[str, tuple[str, float]] = {
    "accent-soft": ("accent", 0.14),
    "accent-line": ("accent", 0.50),
    "amber-soft": ("amber", 0.12),
    "amber-line": ("amber", 0.45),
    "violet-line": ("violet", 0.35),
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"bad hex color: {value!r}")
    return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgba(name: str, alpha: float, theme: str = "space") -> str:
    """把 token 颜色转成 CSS rgba()，供描边/半透明底使用。"""
    r, g, b = hex_to_rgb(theme_colors(theme)[name])
    return f"rgba({r},{g},{b},{alpha:g})"


def theme_colors(theme: str = "space") -> dict[str, str]:
    return THEMES.get(theme, COLORS)


def theme_options() -> list[dict[str, str]]:
    """给设置页下拉用：[{"id": "space", "label": "深空"}, ...]"""
    return [{"id": key, "label": THEME_LABELS.get(key, key)} for key in THEMES]


def theme_css(theme: str = "space") -> dict[str, str]:
    """一套配色展开成 {css 变量名: 值}（不含字号/间距），供 JS 即时换肤。"""
    colors = theme_colors(theme)
    out = dict(colors)
    out.update({name: colors[target] for name, target in ALIAS_VARS.items()})
    out.update({name: rgba(color, alpha, theme) for name, (color, alpha) in ALPHA_VARS.items()})
    return out


def css_variables(theme: str = "space") -> str:
    """生成 :root { --bg: ...; } 供 web/ 直接注入。"""
    lines = [f"  --{name}: {value};" for name, value in theme_colors(theme).items()]
    lines += [f"  --{name}: {theme_colors(theme)[target]};" for name, target in ALIAS_VARS.items()]
    lines += [
        f"  --{name}: {rgba(color, alpha, theme)};" for name, (color, alpha) in ALPHA_VARS.items()
    ]
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
