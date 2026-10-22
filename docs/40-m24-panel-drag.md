# M24 面板可拖动与位置记忆

## 动机

面板一直是被动摆放的：待机时钉右下角、跟随宠物时按 `follow_offset` 自动算位置，
用户没法把它挪到顺手的地方（比如副屏、屏幕上部）。
计划里 P1 的「跟随框记住拖拽偏移」说的就是这件事。

M24 让面板可以用标题栏拖动，拖过之后**记住位置并停止自动摆放**（钉住）；
想回到默认位置：右键待机球/托盘菜单「面板回到默认位置」，或 `mascot.exe ctl reset-panel`。

## 改动

### 前端（`src/mascot_app/web/`）

- `panel.html`：`<header class="bar pywebview-drag-region" title="拖动可移动面板">`。
  `.pywebview-drag-region` 是 pywebview 的拖拽区标记：body 上常驻的 mousedown 监听会沿 DOM 向上找这个类，
  命中后把鼠标移动折算成窗口位置（`pywebviewMoveWindow` → `window.move`）。
- `css/base.css`：`.bar{cursor:grab}` / `.bar:active{cursor:grabbing}`，`.bar .avatar,.bar button{cursor:pointer}`。

### 窗口拖动（`src/mascot_app/runtime.py`）

pywebview 6.2.1 的 WinForms `move()` 有 bug：
`SetWindowPos(handle, None, x, y, None, None, flags)` 把 `None` 传给了 int 参数，
拖动时 `js_bridge_call` 抛 `ctypes.ArgumentError: argument 5: TypeError: wrong type`，窗口纹丝不动（日志里能看到）。
所以 run() 里创建完窗口就接管：

```python
self._panel.move = self._move_panel_from_js  # type: ignore[method-assign]
```

`_move_panel_from_js(logical_x, logical_y)`：JS 给的是逻辑像素，按 `win32.window_dpi(hwnd)/96` 换算成物理像素后
调 `win32.move_window()`（我们自己的 SetWindowPos 封装）。

### 位置记忆与「钉住」（`runtime.py`）

- `load_panel_pos()` / `save_panel_pos()`：`runtime.json` 的 `panel_pos` 键（与 `ball_pos` 同文件，读-改-写保留其它键）。
- `_place_panel()` 顺序：
  1. 先量真实窗口矩形（顺手解决 DPI 物理/逻辑尺寸问题）；
  2. **发现位置不是我们放的**（与 `_last_panel_rect` 差 >2px）→ `_adopt_panel_pos()`：记 `panel_pos`、停止跟随/贴角；
  3. 有 `panel_pos` → 夹进所在屏工作区后就位（不会被拖到屏幕外找不回来）；
  4. 没 `panel_pos` → 原逻辑：待机右下角 / 跟随宠物。
- 落盘延后：拖动中每帧写 `runtime.json` 太吵，`_panel_dirty` 标记 + 位置稳定后的下一次 `_place_panel` 才写一次。
- 复位：`CMD_RESET_PANEL = 1008`（托盘/待机球右键菜单「面板回到默认位置」）与 ctl 动作 `reset-panel`，
  清 `panel_pos`、清 `_last_panel_rect` 后立即重摆。

## 验收（`scripts/verify_m24.py`，Windows 10/10 PASS）

无宠物启动（null provider），全程真实窗口：

| 检查 | 结果 |
| --- | --- |
| 面板可见（ctl to-panel → idle_open） | true（rect 2048,942 488×634） |
| 初始没有 panel_pos | true |
| 真实鼠标拖标题栏 | true（窗口从 2048,942 移到 1488,612 一带） |
| panel_pos 落盘 | true |
| 拖完 1.5s 不被自动摆回 | true |
| 重启后位置恢复 | true（±4px） |
| ctl reset-panel 回右下角 | true（2048,942 = 2560-488-24, 1600-634-24） |
| panel_pos 被清掉 | true |
| 两次退出码 | 0 / 0 |

回归：verify_m13 / m14 / m15 / m16 全部 exit 0（点球开面板、待机球拖动/吸附/菜单、历史持久化不受影响）。
Linux 门禁：pytest 170 passed / ruff 0 / pyright 0。
证据：`evidence/m24-panel-moved.png`（面板被拖到屏幕中部，标题栏 tooltip「拖动可移动面板」）。

## 坑

1. **pywebview 的 move 在这版是坏的**：只加 `.pywebview-drag-region` 会看到窗口抖一下不动，日志里是 `SetWindowPos` 的 ctypes 报错。
   不升级依赖（升级会牵动别的验收），直接接管 `window.move`。
2. **不要靠 `_last_panel_rect` 判断「我们刚移动过」**：用户拖动正是通过差值发现的；我们自己 move 后立刻更新 `_last_panel_rect`，两边不冲突。
3. **拖动中写盘**：每帧一次 JSON 原子写会拖慢拖动，改成稳定后写一次；`panel_moved` 日志只在一次拖动开始时打一条。
4. **钉住 ≠ 跟随**：拖过之后面板不再跟随宠物/贴角，这是设计取舍（要「跟着但偏移」得再存相对偏移，见遗留）。

## 遗留

- 钉住是绝对坐标：换显示器/分辨率后位置会被夹回工作区，但不会按比例迁移。
- 没有「双击标题栏最大化/还原」（面板本来固定尺寸）。
- 「跟随模式下的相对偏移记忆」没做（当前只有绝对钉住）。

