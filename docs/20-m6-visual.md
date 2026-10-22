# M6 视觉对齐：像素时钟球（还原原版视觉基线）

## 1. 为什么做

用户 2026-10-22 早上的反馈：**"感觉效果如此之差，远不如原版"**。
复盘第一版的做法：M1 的球是"渐变球 + 高光"（`mascot_render/ball.py`），
而原版 `E:/TX-Pet/src/orbital_render.py` 是像素美术（44 格、硬色阶、
NEAREST 放大、0/255 alpha、指针 + 刻度 + 星光）。渐变球在 96px 下
既没有信息量（看不出是时钟），也没有 IP 辨识度，所以观感差距很大。

结论：**像素语言是视觉基线，不是"低配占位"**。第一版把它当占位是判断错误。

## 2. 做了什么

新增 `src/mascot_render/clock.py`：

| 元素 | 做法 |
| --- | --- |
| 球体 | 3 段实色带 + 月牙高光 + 底部台阶反光 + 1 格描边（向光偏移） |
| 发光 | 阶梯实色十字（2 格），不用 alpha 光晕 |
| 表盘 | 深海军蓝 + 12 刻度（3 的倍数画短线，其余单像素点） |
| 指针 | 时=短粗(3格)、分=中(2格)、秒=细长(1格)，共用青色家族 |
| 星光 | 时/分位置各一颗像素十字星；大星带射线，秒针靠近刻度时点亮 |
| 像素纪律 | 低分辨率网格绘制 → alpha 二值化(0/255) → `Image.Resampling.NEAREST` 放大 |

- 调色板进 token 单源：`mascot_core/tokens.py` 新增 `PIXEL`（青）与
  `PIXEL_AMBER`（降级）。像素语言需要 5 个硬色阶，和 CSS 的连续色不冲突，
  但同样"改颜色只改一处"。
- `render_clock(size, now=…, now_ts=…, stuck=…, hover=…)`：时间由调用方注入，
  `now_ts` 固定时输出**完全确定**，所以能做跨平台快照测试。
- `render_orbit_frame(...)`：整帧（像素彗尾 + 球），先实现、暂未接入运行时
  （需要更大的透明窗口 + 命中测试，见 §5）。
- 球径 **96 → 128px**：96px 下 3 格粗的时针会糊成一块，128px 可读性明显更好
  （对比图 `evidence/m6-clock-sizes.png`：96 / 128 / 160）。

## 3. 顺带修掉的语义 bug

`--provider null` 之前会被健康探测标成 **降级**：NullProvider 的 health 本来就是
DEGRADED（"没有后端"），而 M5 的修复又让探测无条件上报，于是"显式不要后端"的
演示/截图全变成红点 + 琥珀横幅。现在 `_poll_provider` 对 `provider.name == "null"`
直接返回，只在 provider_detail 里写"null provider（显式离线模式）"。
降级横幅只表达"**配了后端但连不上**"。

## 4. 验证

- Linux：ruff 0 / pyright 0 / pytest **84 passed**（新增 8 条 clock 测试 + 4 条快照）。
- Windows：同套测试 84 passed（1 skip）；真机 demo（`--provider null --demo`）
  环绕态截图 `evidence/m6-orbital.png`：宠物旁的像素时钟球，指针指向当前时间。
- 快照：`tests/snapshot/baseline/clock-1010|1200|1545|stuck.png`；画廊
  `evidence/m3-render-gallery.png`（现含 13 个用例）。
- 可复现：
  ```bash
  uv run python scripts/make_baselines.py         # 改了绘制才需要
  uv run pytest -q                                # Linux
  # Windows 开发副本
  cd /mnt/c/Users/Public/mascot && ./venv/Scripts/python.exe -m pytest app/0.1.0/tests -q
  ```

## 5. 还没做（下一步）

1. **彗尾**：`render_orbit_frame` 已能用，但要把它接进运行时需要把球窗口从
   128×128 放大到"轨道直径"窗口，并用命中测试让球以外的区域点击穿透
   （`mascot_core/hit.py` 的 `hit_test` + WM_NCHITTEST），否则会挡住桌宠点击。
2. **面板美术**：面板目前是纯排版（无立绘/头像），比原版"缺画面"。下一步做
   头部头像区（像素风徽标）+ 状态灯动效，再接 docs/12 的基线包。
3. 旧 `render_ball`（渐变球）目前只剩 badge 和快照在用，接入状态灯后即可删除。
