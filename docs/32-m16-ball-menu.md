# M16 待机球右键菜单、边缘吸附、回到右下角

M14 把待机球做成像素时钟并允许拖动后，留下两个体验缺口：拖到屏幕边缘时球会停在离边缘
几像素的"悬空"位置，且没有任何办法把它送回默认角落；球上也没有右键菜单，只能绕到托盘图标。
M16 补这三件事。

## 1. 边缘吸附

`src/mascot_app/runtime.py` 的 `_on_ball_drag_end(x, y, moved)` 重写：

- 只有真的拖动过（`moved=True`）才处理，纯点击走原路径（打开面板）。
- 用松手点所在屏的 `win32.work_area(...)`（不是主屏）算边界，多屏各算各的。
- 吸附阈值 `snap = 12`：左/上边距 ≤12 → 贴 8px；右/下边距（`wx+ww-(x+BALL_SIZE)` /
  `wy+wh-(y+BALL_SIZE)`）≤12 → 对齐到工作区右/下再退 8px；其余位置原样保留。
- 吸附后的位置立即 `_ball.move()` 并 `save_ball_pos()`，所以重启后仍在贴边处。

留 8px 而不是死死贴着：贴 0px 时球和屏幕边缘完全重合，视觉上像被裁掉一块。

## 2. 右键菜单

菜单只在待机球上出现（轨道态的球是装饰，右键无意义）。

- `src/mascot_win/layered.py`：`LayeredWindow` 增 `_menu_builder` / `_menu_command`,
  `enable_context_menu(builder, on_command)` 注册；`_on_message` 处理 `WM_RBUTTONUP`
  （新增常量 `WM_RBUTTONUP = 0x0205`），有 builder 才弹。
- `_popup_menu()`：`CreatePopupMenu` + `AppendMenuW`（空文案当分隔线、勾选态用 `MF_CHECKED`）
  → `SetForegroundWindow(hwnd)`（否则点空白处菜单收不起来）→
  `TrackPopupMenu(TPM_RIGHTBUTTON | TPM_RETURNCMD)` → `PostMessage(WM_NULL)`（新增常量
  `WM_NULL = 0x0000`，让窗口不再占前台）→ 有返回值就回调 `on_command(int(cmd))`。
  `TPM_RETURNCMD` 让选择直接以返回值给出，不用再等 `WM_COMMAND`。
- 运行时直接复用托盘菜单的构造器 `_build_tray_menu` 与分发器 `_on_tray_command`，
  所以球菜单和托盘菜单永远同源（新增项只写一处）。
- 新增 `CMD_RESET_BALL = 1007`：「小球回到右下角」，插在「开机自启」与「退出」之间
  （中间加分隔线）。
- `_render_idle_ball` 里 `enable_drag` 之后 `enable_context_menu(...)`；
  `START_FRAMES` 特效里 `disable_drag()` 之后把菜单换成空构造器 + 空回调，轨道态右键不弹。

## 3. 回到右下角

`save_ball_pos` 签名放宽成 `tuple[int, int] | None`：`None` 时从 `runtime.json` 里
`pop("ball_pos")`（而不是写一个假的默认坐标），这样"没拖过"和"拖过又复位"状态一致。
`_on_tray_command` 的 `CMD_RESET_BALL` 分支把 `_ball_pos` 清空、落盘、重新渲染待机球，
球就回到 `_bottom_right(BALL_SIZE)` 的默认角落（右下 -24px 余量，与 M13 一致）。

## 验收（scripts/verify_m16.py，7/7 PASS）

| 检查 | 结果 |
| --- | --- |
| `idle_ball_visible` | ✅ 球 2408,1448 128×128 |
| `edge_snap_x` | ✅ 拖到右边缘后 x = 工作区右(2560) - 128 - 8 = 2424 |
| `snapped_ball_pos_saved` | ✅ `runtime.json` 的 `ball_pos == [2424,1448]` |
| `context_menu_opens` | ✅ 枚举到可见的 `#32768` 菜单窗口 |
| `reset_to_bottom_right` | ✅ 键盘选第 6 项后回到 2408,1448（= 2560-128-24, 1600-128-24） |
| `ball_pos_cleared` | ✅ `runtime.json` 里 `ball_pos` 键被删掉 |
| `exit_code` | ✅ 0 |

回归：`verify_m13.py` 10/10、`verify_m14.py` 9/9、`verify_m15.py` 14/14 全过
（拖动/点击/位置记忆/历史不受影响）。Linux：ruff 0 / pyright 0 / pytest 全绿。

证据：`evidence/m16-menu.png`（球上右键弹出的菜单，可见分隔线与「小球回到右下角」）、
`evidence/m16-edge-snap.png`（拖到右边缘后贴边 8px 的像素时钟球）。

## 坑

1. **菜单要能"点别处收起"，必须 `SetForegroundWindow` 后再 `TrackPopupMenu`**，
   否则菜单会一直挂在屏幕上；关闭后补一个 `PostMessage(WM_NULL)` 释放前台，
   这和托盘菜单的处理是同一套。
2. **菜单里不能用 `WM_COMMAND` 分发**：`TPM_RETURNCMD` 已经通过返回值给出选择，
   再挂 `WM_COMMAND` 会双触发。这里统一走返回值。
3. 验收脚本用键盘选菜单项（`VK_DOWN` ×6 + `VK_RETURN`）验证"回到右下角"，
   比按坐标点菜单项稳（菜单尺寸随 DPI/字体浮动）。

## 遗留

- 吸附只在松手时做，拖动过程中球不会被边缘"吸住"（无橡皮筋手感）。
- 没有双击复位（只有菜单项）。
- 面板 idle 位置仍不跟随球（M13 起就是固定右下角）。
- 菜单无图标、无快捷键。
