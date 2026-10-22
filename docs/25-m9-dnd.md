# M9 · 免打扰与多显示器定位

## 1. 为什么要做

两件"平时不显眼、真用起来就疼"的事：

1. **免打扰（DND）**：桌宠跟随很容易在工作时反复弹面板。用户明确要"干净"，docs/12 氛围包也把 DND 列为一项。
   这里不给新 UI，只给托盘一个勾选项 + `ctl dnd on|off`。
2. **多显示器定位**：M2 起面板定位用的是主屏尺寸（`screen_metrics()`）。宠物在副屏时，
   跟随框会被 `clamp_rect` 拽回主屏——插上外接显示器就立刻暴露。M9 改成"取宠物所在显示器的可用工作区"。

## 2. 免打扰语义

```
_dnd = False  默认
    开启：PET_FOUND 的 SHOW_PANEL 副作用被跳过（日志 "dnd: 跳过自动弹面板"），
          已打开的面板立刻隐藏；跟随轮询与球体动画照常；
          托盘双击 / "显示面板" / ctl to-panel 仍可手动打开（手动优先于免打扰）。
    关闭：不自动补弹面板，回到"下次宠物出现时自动显示"。
```

状态机本身不改——DND 是"副作用过滤器"，不是新状态。这样任何后续新增的弹窗都能用同一条规则约束。

入口：

- 托盘菜单新增 `免打扰`（勾选态来自 `snapshot().dnd`），tip 追加"（免打扰）"；
- `mascot ctl dnd on|off`（走 control.json，与托盘共享同一命令 `toggle_dnd`）；
- `snapshot()` 新增 `dnd` 字段（面板/验收脚本/状态文件都能读）。

## 3. 多显示器定位

新增 `win32.work_area(x, y) -> (x, y, w, h)`：

```python
MONITORINFO(rcMonitor, rcWork) + MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
→ GetMonitorInfoW → 返回 rcWork（已排除任务栏）
```

`_place_panel()` 改为以**宠物中心点**查它所在显示器的工作区，再喂给 `follow_rect(..., Screen(w, h, x, y))`。
`Screen` 本来就带原点偏移，`clamp_rect` 也已支持负坐标多屏，所以只换数据源即可。

顺带修掉任务栏遮挡：面板贴屏幕底边时不再压到任务栏下面。

## 4. 验证

- 单元测试：`test_dnd_toggle_hides_panel_and_skips_auto_show`（dnd 翻转、tip、PET_FOUND 后仍 tracking）、
  `test_follow_rect_clamped_into_secondary_monitor_work_area`（副屏原点 2560 起，面板不越界）、
  `test_work_area_fits_inside_screen_and_excludes_taskbar`（平台测试：工作区在屏幕内、高度 ≤ 屏高）。
- 真机验收 `scripts/verify_m9.py`（8 项全过）：
  tracking → 面板可见 → `ctl dnd on` → `dnd=true` 且面板隐藏 → `ctl to-ball` 仍进 orbital
  → `ctl dnd off` → `ctl to-panel` 回 tracking 且面板重新可见 → `ctl stop` → 退出码 0。
- Windows 全量测试 93 passed / 1 skipped；Linux ruff 0 / pyright 0 / pytest 87 passed。

## 5. 遗留

- DND 不持久化（重启回到关闭）。考虑放进 `settings`，但它是"临时心情"而非工程配置，先不做。
- 只处理了自动弹面板；将来若有气泡通知，也应走同一条副作用过滤。
- 多显示器只在单屏机器上验证了"工作区取对"（rcWork 比屏幕小 40px 任务栏），
  真正的双屏摆位需要外接显示器才能实测，代码路径已按坐标偏移实现。
