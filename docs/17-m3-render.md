# 17 · M3 渲染迁移与快照基线（一份 token，两套渲染）

> 阶段：M3（已完成）
> 涉及文件：`src/mascot_core/tokens.py`、`src/mascot_app/web/panel.html`、`src/mascot_app/runtime.py`、
> `src/mascot_render/{ball,gallery}.py`、`scripts/make_baselines.py`、`tests/snapshot/`、`tests/unit/test_token_contract.py`

## 1. 目标

旧实现里一个青色写在三处：HTML 的 CSS、Python 的 PIL 绘制、截图脚本。M3 把它收敛成一条硬契约：

> **颜色/字号/圆角/动效只允许定义在 `mascot_core.tokens`，HTML 与 PIL 都从它派生。**

再配上像素快照，把“球长什么样”变成可回归的测试，而不是靠人眼每天比截图。

## 2. CSS 侧：占位符注入

`panel.html` 里不再有 `:root{...}`，只有一行占位：

```html
<style>
  /*__TOKENS__*/
  ...
```

`runtime.load_panel_html()` 读取 HTML 后把占位符替换成 `tokens.css_variables()` 的输出（`:root { --bg: #0e1116; ... }`）。因此：

- 打包后的真实面板里 CSS 变量齐全；
- HTML 源码里搜不到任何 `#0e1116` 这类字面量，想改色只能改 Python；
- `css_variables()` 现在还产出派生变量（半透明描边/底色）：
  `--accent-soft: rgba(86,212,221,0.14)`、`--accent-line: rgba(86,212,221,0.5)`、
  `--amber-soft: rgba(227,179,65,0.12)`、`--amber-line: rgba(227,179,65,0.45)`，
  由 `tokens.ALPHA_VARS: dict[str, tuple[str, float]]` 声明（token 名 + alpha）。

CSS 里所有硬编码都已换成 `var(--x)`，并且使用真实存在的变量名（M2 面板曾用 `--muted`/`--r-chip`，其实从未定义，靠浏览器 fallback 才“看起来正常”——这类幽灵变量会让主题化悄无声息地失效）。

## 3. PIL 侧：球与状态灯

`render_ball(size=96, phase, stuck)`：

- 主色 = `pixel_palette(6).accent`（`--accent` 的分档调色板）；`stuck=True` 时用 `COLORS["amber"]`；
- 高光/芯用 `COLORS["text"]`，不再写死 `(255,255,255)`；
- **修掉一个真实观感 bug**：原来高光圆用 `ImageDraw` 直接画在球体上，`fill=(*color, alpha)` 是“替换像素”而不是“叠加”，结果球心变成半透明的灰点。现在高光与芯画在独立图层，再 `Image.alpha_composite` 合成，球看起来是有体积的玻璃球（见 `evidence/m3-render-gallery.png` 第一排的呼吸变化）。

`render_badge(size=18, state)` 的四态颜色改为查表 `BADGE_COLORS`：`idle/working → accent`、`awaiting → amber`、`error → red`。

## 4. 快照基线（可回归的“长相”）

`src/mascot_render/gallery.py` 是测试与文档共用的用例表：

| 用例 | 说明 |
| --- | --- |
| `ball-phase-0.00/0.25/0.50/0.75` | 呼吸相位四帧（96px） |
| `ball-stuck` | 等待用户时的琥珀球 |
| `badge-idle/working/awaiting/error` | 状态灯四态（18px） |

`scripts/make_baselines.py` 生成 9 张基线到 `tests/snapshot/baseline/`，同时输出暗底拼图 `evidence/m3-render-gallery.png` 供人工检查；`--check` 只报告缺失。

`tests/snapshot/test_render_snapshot.py` 用 `ImageChops.difference` 比像素，容差：

- 每通道平均绝对误差 `MEAN_TOL = 2.0`（0–255）；
- 单像素最大误差 `MAX_TOL = 48`（抗锯齿边缘的正常抖动）。

容差不是为了掩盖改动：真正改了绘制（比如刚才的合成修复）就必须重跑 `make_baselines.py` 并提交新基线，diff 里能看见“长相变了”。

## 5. 契约测试

`tests/unit/test_token_contract.py` 四条，把“一份真源”钉死：

1. 占位符必须被替换，且页面里只有一个 `:root`；
2. HTML 里 `var(--x)` 用到的每个变量都必须在 Python 侧声明（幽灵变量直接失败）；
3. `:root` 之外的 CSS 里不允许出现 `#rrggbb` 字面量；
4. 状态灯配色表引用的 token 名必须存在于 `COLORS`。

第 2 条是这次最有价值的检查：它抓的正是 M2 里那批从来不存在的变量名。

## 6. 验证

```
Linux:    ruff 0 / pyright 0 / pytest 50 passed（含 9 条快照）
Windows:  pytest tests/snapshot -q -> 9 passed（Pillow 13.0.0，与 Linux 同版本）
真机:     m3-panel.png —— 面板配色与 M2 一致，说明 token 注入未破坏样式
          m3-render-gallery.png —— 四帧呼吸 + 琥珀等待球 + 四态状态灯
```

## 7. 遗留

- 字号/间距 token 已进 CSS 变量，但 JS 侧没有消费（面板不动态算尺寸）——可在 M4 面板拆分时统一；
- 球还没有帧动画（现在靠相位实时算，CPU 开销可忽略，但“像素风”需要离散帧），P2 再议；
- 快照只覆盖球与状态灯，面板整体外观仍是人眼验收（WebView 截图不稳定，M5 打包后可做固定尺寸快照）。
