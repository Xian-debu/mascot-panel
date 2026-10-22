# M26 启动时面板窗口其实没藏住

## 动机

M25 验收时发现一个不该存在的东西：无宠物启动（待机球模式）6 秒后枚举窗口，
`mascot-panel` 的 hwnd 明明存在，`IsWindowVisible` 与 `WS_VISIBLE` 位都是真，
rect 覆盖 2048,942 488×634（正好是待机面板该在的位置），只是屏幕上画不出内容
（WebView2 还没渲染完）。

也就是说 `webview.create_window(..., hidden=True)` 并没有真的把窗口藏住。
窗口虽然看不见内容，但它是一个 `topmost` 的普通窗口：可能拦鼠标、可能被 Alt+Tab / 任务栏
看见、也可能在别的程序截图里以空白块出现。这类「看不见但存在」的窗口是包袱，
M26 就是把它真正藏起来，并且**只在状态机需要面板时才显示**。

## 根因

pywebview 6.2.1 `platforms/winforms.py` 里 `create_window()` 的 hidden 分支：

```python
if window.hidden:
    browser.Opacity = 0
    browser.Show()      # 先必须 Show 一次，WebView2 才肯初始化
    browser.Hide()
    browser.Opacity = 1
```

`Show` + `Hide` 之后窗口本该是隐藏的，但 WebView2 初始化完成 / HTML 导航完成后
内部还会再 `Show` 一次（源码另一处注释就提到「window is started hidden and shown on
Navigating event」）。所以 Python 侧以为藏了，Win32 侧最终还是 `WS_VISIBLE`。

## 改法（两层）

`src/mascot_app/runtime.py`：

1. **GUI 线程起来时兜一次**：`_on_gui_start()` 里如果状态机当前是 `State.IDLE`
   （待机球模式，面板本来就该藏着），就 `win32.show_window(panel_hwnd, False)`，
   并打 boot 标记 `panel_hidden_at_start`。
2. **工作线程持续纠正**：主循环每轮调 `_enforce_panel_hidden(now)`，节流 0.3s；
   只要状态是 `State.IDLE` 且窗口 `is_visible()`，就再藏一次。这样即使 pywebview
   之后又 Show，也会在几百毫秒内被纠正。

判定「该不该藏」用**状态机状态**而不是自己维护的布尔标志：
`self._machine.state is State.IDLE` 是唯一需要面板隐藏的状态；
`IDLE_OPEN / TRACKING / ORBITAL / DEGRADED` 都要面板可见。
第一版用的是 `self._panel_shown` 标志（在 `_effect` 里设），结果撞上竞态：
状态机先记 `state=idle_open`、副作用在下一拍才把标志置真，
而 `_on_gui_start` 恰好在这个窗口里跑，于是把「用户刚要求显示」的面板藏了
（boot 标记里能看到 `state_idle_open:625` 早于 `panel_hidden_at_start:687`）。
改成直接读状态机状态后消失。

`src/mascot_win/win32.py` 不需要改：`show_window` / `is_visible` 已有。

## 验收（`scripts/verify_m26.py`，7 项）

WINDOWS 10 项判定（无宠物 null provider）：

| 项 | 实测 |
| --- | --- |
| `panel_hwnd_found` | true（启动 6s 能找到 hwnd） |
| `panel_hidden_at_start` | true（`WS_VISIBLE` 位 = 0，`IsWindowVisible` = false） |
| `panel_is_visible_api` | false |
| `panel_ws_visible` | false |
| `panel_not_blocking_clicks` | true（`WindowFromPoint(面板中心)` 返回的是别的窗口 5705522） |
| `stays_hidden` | true（再等 2s 仍 `WS_VISIBLE` = false，没有被 pywebview 又 Show） |
| `state_after_click` | `idle_open`（点球照常开面板） |
| `panel_shown_ws_visible` | true（这次是真的是可见） |
| `panel_hidden_again` | true（`ctl to-ball` 后又被藏回去） |
| `exit_code` | 0 |

面板 rect 仍是 2048,942 488×634（位置逻辑没动，只是可见性对了）。
回归：`verify_m13/m14/m15/m16/m24/m25` 全部 exit 0、`ok: true`。
Linux 门禁：ruff 0、pyright 0、pytest 通过。

## 坑

1. **`hidden=True` 不能当契约**。跨版本行为会变（WebView2 初始化时机不同），
   要自己在 Win32 侧确认并纠正；验收也不要信 Python 侧的标志，要 `GetWindowLongW(GWL_STYLE)`。
2. **谁要面板，用状态机状态判断**。用一个额外布尔标志会和状态机的「先记状态、后跑副作用」
   顺序打架，出现「刚显示就被藏」。
3. **节流不能省**。`_enforce_panel_hidden` 每轮循环都跑会一直 `IsWindowVisible` + `ShowWindow`，
   在 10fps 下也还行，但 0.3s 节流足够且不抖动。
4. **验收要用状态而不是「窗口看得见」**。M25 已经把「面板没打开」的判据从
   `IsWindowVisible` 换成 `state != idle_open`；M26 之后两者一致了，但保留状态判据更稳。

## 遗留

- 面板窗口在 `IDLE_OPEN` 时依旧是 `topmost`（跟随宠物时压在宠物窗口上方，属设计），
  没有做「激活时再置顶」。
- 窗口没有从任务栏隐藏（`WS_EX_TOOLWINDOW` 已在 `_ensure_panel_hwnd` 里设过，
  但只在第一次拿到 hwnd 时设，若 pywebview 重建窗口需要重设——目前没遇到重建）。
- 关闭 WebView2 的「透明 hack」路径未验证（本项目一直走 `hidden=True` 分支）。
