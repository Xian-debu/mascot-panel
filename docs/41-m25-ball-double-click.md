# M25 待机球单击开面板 / 双击回右下角

## 为什么做

进度报告的已知缺口里有「待机球吸附只在松手时生效（无拖动中橡皮筋、无双击复位）」。
双击复位是用户最容易想到的"把球放回去"手势——比右键菜单少两步。

但待机球上单击是"打开面板"，两个手势共用同一个触发点（按下又抬起、且没拖动），
所以必须自己判双击。

## 为什么不用 WM_LBUTTONDBLCLK

Win32 的双击消息要求窗口类带 `CS_DBLCLKS`，而且系统**仍会先送一次普通单击消息**。
把它接上就会出现"第一次单击已经把面板打开了，双击再复位球"的副作用——顺序错了，没法撤回。
所以自己数点击：第一次点击先挂起，350ms 内来第二次算双击，超时算单击。

代价是单击开面板多等约 350ms（窗口 + 最坏一轮循环 100ms）。

## 改动

### 纯逻辑 `src/mascot_core/click.py`（新增）

- `CLICK_WINDOW_MS = 350.0`，`SINGLE = "single"`，`DOUBLE = "double"`。
- `ClickGate(window_ms=350)`：
  - `click(now_ms)`：第一次返回 `None` 并挂起；窗口内第二次返回 `"double"` 并清空。
  - `tick(now_ms)`：挂起的点击超时则返回 `"single"` 并清空，否则 `None`。
  - `reset()`：放弃挂起（拖动开始等场景）。
  - `pending`：是否有挂起点击。
- 无 Win32 依赖，Ubuntu CI 可单测（`tests/unit/test_click.py`，8 项）。

### `src/mascot_app/runtime.py`

- `self._click_gate = ClickGate()`。
- 球的 `on_click` 从 `lambda: self.post(Event.CLICK_BALL)` 换成 `self._on_ball_click`：
  - 非 `IDLE`（跟随面板/轨道球）仍然立刻 `post(CLICK_BALL)`，行为与 M13 完全一致；
  - `IDLE` 时喂给 `ClickGate`，返回 `DOUBLE` 就 `_reset_ball_to_corner()`（不打开面板）。
- 工作线程循环每轮 `tick(now_ms)`，返回 `SINGLE` 才 `post(CLICK_BALL)`。
- `_reset_ball_to_corner()`：清 `_ball_pos`、`save_ball_pos(None)`、重渲染待机球（回右下角）、日志 `ball_reset`；托盘菜单「小球回到右下角」也改成调它（去重）。
- `_on_ball_drag()` 开头 `self._click_gate.reset()`：手指已经拖动了就不是点击，别在松手 350ms 后突然弹面板。

## 验收（`scripts/verify_m25.py`，11 项）

| # | 断言 | 实测 |
|---|---|---|
| 1 | `idle_ball_visible` | true |
| 2 | `ball_starts_in_corner` | 2408,1448（2560-128-24, 1600-128-24）|
| 3 | `dragged_away_from_corner` | 真实鼠标拖到 789,469 |
| 4 | `drag_pos_saved` | runtime.json `ball_pos=[789,469]` |
| 5 | `double_click_resets_to_corner` | 双击后回 2408,1448 |
| 6 | `ball_pos_cleared` | `ball_pos` 键被删 |
| 7 | `panel_not_opened` | 双击后状态仍是 `idle` |
| 8 | `single_click_opens_panel` | 随后单击 → `idle_open` |
| 9 | `panel_rect_after_open` / `panel_on_screen` | 2048,942 488×634 在屏内 |
| 10 | `exit_code` | 0 |
| 11 | 回归 | `verify_m13/m14/m15/m16/m24` 全 `ok=true`、exit 0 |

Linux 门禁：`pytest 178 passed / 1 skipped`、`ruff 0`、`pyright 0`。

## 坑

1. **双击不是一条独立消息**：两次点击各自都会走 `WM_LBUTTONUP` → `on_click`，
   所以 `ClickGate` 必须对"每一次点击"调用，而不是监听某个双击事件。
2. **拖动要先清挂起**：单击后 350ms 内开始拖动，若不 `reset()`，松手后会把面板弹出来。
3. **面板窗口从启动就是 `WS_VISIBLE`**：pywebview 的 `create_window(hidden=True)` 在这个版本里
   并没有真的把窗口藏起来（探针实测启动 6s 时 `ws_visible=true`，rect 228,228 488×634，但画不出内容）。
   所以验收里不能拿 `IsWindowVisible` 当"面板没打开"的证据，只能看 `state`。这条已记入遗留。

## 遗留

- 单击开面板多约 350ms 延迟（双击窗口的必然代价）；`CLICK_WINDOW_MS` 是常量，未做成配置。
- 轨道球/跟随面板仍是"一点即回面板"，没有双击手势（那里单击就是回面板，不需要区分）。
- 启动时面板窗口 `WS_VISIBLE=true` 但不可见，是否拦截鼠标点击未验证（不影响本次验收，留待 M26）。
