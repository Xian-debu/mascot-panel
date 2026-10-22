# M13 待机形态（宠物不在时也看得见、能聊天）

## 为什么做

M12 之前的状态机只有 idle / tracking / orbital / degraded：宠物（游戏）没开时进程虽然活着，
但**屏幕上什么都没有**——球不显示、面板也不显示，用户只能靠托盘图标或 `ctl status` 才知道它还在跑。
实际使用里“先开桌宠、后开游戏”是很常见的顺序，这个空档期完全不可见，等于软件没启动。

## 状态机改动

新增第五个状态 `State.IDLE_OPEN = "idle_open"`（待机 + 独立面板打开）。

| 当前状态 | 事件 | 新状态 | 副作用 |
| --- | --- | --- | --- |
| idle | CLICK_BALL | idle_open | SHOW_PANEL, HIDE_BALL |
| idle_open | CLICK_CLOCK | idle | HIDE_PANEL, SHOW_BALL |
| idle_open | PET_FOUND | tracking | SHOW_PANEL, HIDE_BALL |
| idle | PET_FOUND | tracking | SHOW_PANEL, HIDE_BALL |
| tracking | PET_LOST | idle | HIDE_PANEL, SHOW_BALL |
| orbital | PET_LOST | idle | STOP_FRAMES（**不再** HIDE_BALL） |
| tracking | CLICK_CLOCK | orbital | SHOW_BALL, HIDE_PANEL, START_FRAMES |
| orbital | CLICK_BALL | tracking | HIDE_BALL, SHOW_PANEL |

两处语义修正：

1. **orbital 收到 PET_LOST 不再收球**。原来宠物消失 → 球也收起来，屏幕上又空了。现在球留在原地
   （下一帧由待机重渲染接管，钉到右下角）。
2. **idle 点球 = 打开独立面板**。之前 idle 下点球没有任何转移（球在但点不动），现在进入 idle_open。

`PROVIDER_READY` 的恢复白名单也加入 idle_open：降级恢复后回到“待机但面板开着”，而不是掉回 idle。

## 运行时改动（src/mascot_app/runtime.py）

- `_STATE_LABEL["idle_open"] = "待机（面板）"`。
- `_idle_anchor(size) -> (x, y)`：取**光标所在显示器**的工作区右下角，留 24px 边距。用 `work_area`
  而不是主屏 `screen_metrics`，副屏也能贴对。
- `_render_idle_ball()`：`render_ball(BALL_SIZE, phase=time.time() % 6.0, stuck=self._degraded)` +
  `set_hit_circle(half, half, half + 2)` + `_idle_anchor` 定位。像素时钟靠 phase 走动，所以 worker
  循环里每秒重渲染一次（`ball_now = self._ball` 局部变量，见踩坑 1）。
- `_place_panel`：`self._pet is None` 时走 idle 分支——**先量真实窗口尺寸再锚定**（见踩坑 2）。
- `_effect` 的 SHOW_BALL：宠物为 None 时调 `_render_idle_ball()`，而不是渲染轨道球。
- worker 启动后：`boot_ball = self._ball`，state 为 idle 时 `show()` + `_render_idle_ball()`，
  这样冷启动没宠物也能立刻看到球。

## 前端

src/mascot_app/web/js/ui.js：`LIGHT`/`LABEL` 加 `idle_open`（都映射到 idle 观感，标签“待机”）；
hint 在 idle_open 显示“宠物没开也能聊”。

## 验收（scripts/verify_m13.py，10 项全过）

用一个“永远找不到宠物”的配置启动，让状态停在 idle：

```bash
MASCOT_PET_PROCESS_NAMES='["__no_such_pet__.exe"]' MASCOT_PET_WINDOW_CLASS='__no_such_class__' \
  python -m mascot_app.cli run --provider null
```

然后依次断言：

| 检查 | 结果 |
| --- | --- |
| idle_without_pet | idle |
| pet_is_none | true |
| idle_ball_visible | true（ball_rect 2408,1448 128×128） |
| click_ball_opens_panel | idle_open（真实 WM_LBUTTONDOWN/WM_LBUTTONUP 打进球的 wndproc） |
| panel_visible | true |
| panel_at_bottom_right | true（panel 2048,942 488×634，工作区 2560×1600，右下各差 24px） |
| ctl_to_ball_returns_idle | idle |
| panel_hidden_after_to_ball | true |
| ctl_to_panel_reopens | idle_open |
| exit_code | 0 |

真机结果 `{"ok": true}`。截图：evidence/m13-idle.png（右下角常驻待机球）、
evidence/m13-idle-panel.png（点球后的独立面板，chip 待机、hint“宠物没开也能聊”）。

## 两个踩坑

1. **pyright 把成员属性窄化成 None**。循环里写 `and self._ball is not None` 之后，else 分支
   （即 `self._ball is None`）会沿回边影响下一轮的 `self._ball.pump()`，报
   `“pump” is not a known attribute of “None”`。改成局部变量 `ball_now = self._ball` 再判断即可
   ——局部窄化不会污染成员属性的类型。
2. **DPI 让“逻辑尺寸”和“物理尺寸”对不上**。`settings.panel_size=(340,460)` 是逻辑尺寸，WebView
   窗口实际物理尺寸是 488×634（150% 缩放）。用逻辑尺寸锚定右下角，面板会溢出屏幕 124/150px。
   修法：锚定前 `win32.get_window_rect(self._panel_hwnd)` 量真实尺寸，取不到才回退。
   另外**验收脚本自己也要 `win32.enable_dpi_awareness()`**，否则 `work_area` 返回的是逻辑坐标
   （1707×1067），和物理矩形比较必然失败——这条坑浪费了一轮排查。

## 遗留

- 待机球的绘制仍是 M3 的渐变球（`render_ball`），还没换成像素时钟（`render_clock`），
  与轨道球风格尚未统一。
- 待机球固定在右下角，不可拖动（拖动仍是 backlog 里的条目）。
- 面板 idle 位置固定右下角，没有记忆用户上次位置。
