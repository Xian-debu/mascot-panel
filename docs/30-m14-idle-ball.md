# M14 待机球：像素时钟 + 可拖动 + 位置记忆

## 为什么做

M13 把待机形态补上了（右下角常驻小球 + 点球开独立面板），但留了三个尾巴：

1. 待机球还是 M3 的**渐变球**（`render_ball`），与轨道球（M6b 的像素时钟 `render_clock`）风格不一致
   ——同一个程序里两种美术风格。
2. 球被钉死在右下角，**不可拖动**。用户如果右下角有别的常驻窗（输入法、下载条、任务栏扩展），
   球就永远被压在下面。
3. 位置**不记忆**：重启又回右下角，第二次还得再挪。

M14 把这三件事一起收掉。

## 运行时改动

### 待机球换像素时钟

`_render_idle_ball()` 从 `render_ball(BALL_SIZE, phase=...)` 改成：

```python
img = render_clock(BALL_SIZE, now_ts=time.time(), stuck=self._degraded, hover=False)
```

指针按真实时间走（不再靠 phase 伪动画），降级时传 `stuck=True`（指针停住，弧变黄）——
和轨道球用同一套时钟渲染，风格、配色、降级语义全部一致。每秒重渲染一次由 worker 循环驱动。

### 拖动（src/mascot_win/layered.py）

`LayeredWindow` 新增拖动能力，只有待机球启用（轨道球是动画，拖它没有意义）：

- `enable_drag(on_drag, on_drag_end=None)` / `disable_drag()`
- `WM_LBUTTONDOWN`：`SetCapture`，记录按下时的光标位置和窗口位置；
- `WM_MOUSEMOVE`（拖动中）：算 `dx/dy`，位移 >3px 才算“真的在拖”（避免手抖把点击变成拖动）；
- `WM_LBUTTONUP`：位移超阈值 → `on_drag_end(pos, moved=True)`，只存位置；
  没超过 → 仍然是点击，`on_click()` 打开面板。

用 `SetCapture`/端到端光标位移而不是 `WM_NCHITTEST` 的 `HTCAPTION`，是为了保留“点一下开面板”
（交给系统拖窗口会吃掉点击事件）。

### 位置记忆（src/mascot_app/runtime.py）

- `runtime.json` 增加一个键 `ball_pos: [x, y]`（与已有的 `dnd`/`paused` 同一个文件）。
- `load_ball_pos() -> tuple[int, int] | None`、`save_ball_pos(pos)`。
- `save_flags` 改成**读-改-写**，避免写 flags 时把 `ball_pos` 冲掉（反过来也一样）。
- `_idle_anchor()` 优先用记住的 `_ball_pos`，但**必须落在某块屏的工作区内**才用（换显示器/改分辨率
  后旧坐标可能已经在屏幕外，这时回退到右下角）。
- 拖动时实时夹到当前屏工作区（`_on_ball_drag`），松手才落盘（`_on_ball_drag_end`）——
  拖动过程每帧写文件没必要。
- 待机**面板**不跟随球位置：`_place_panel` 的 idle 分支仍贴 `_bottom_right()`，
  球可以拖到任意角落而面板保持右下角（面板是 488×634，跟着球跑会更难用）。

## 验收（scripts/verify_m14.py，9 项全过）

同样用“永远找不到宠物”的配置启动，让状态停在 idle，然后用**真实鼠标注入**（`SetCursorPos` +
`mouse_event`）而不是伪造消息，验证整条链路：

| 检查 | 结果 |
| --- | --- |
| idle_ball_visible | true（ball_rect 2408,1448 128×128） |
| ball_is_clock_size | true（128px，与 `BALL_SIZE` 一致） |
| drag_moved_ball | true（拖动后 ball_rect 2248,1328，位移 -160/-120） |
| state_still_idle | true（拖动不改变状态机） |
| ball_pos_saved | true（runtime.json 里 `ball_pos: [2248, 1328]`） |
| click_after_drag_opens_panel | idle_open（拖完再点一下，仍能开面板） |
| restart_ball_visible | true |
| position_restored | true（重启后球回到 2248,1328 ±12px） |
| exit_code | 0 |

回归：`scripts/verify_m13.py` 仍 10/10 PASS（拖动没破坏“点球开面板”、面板仍贴右下角）。

截图：`evidence/m14-ball-zoom.png`（4× 放大的像素时钟球，青色指针 + 刻度，与轨道球同款）、
`evidence/m14-idle-ball.png`（桌面右下角实拍）、`evidence/m14-dragged.png`（拖到屏幕中部后）。

## 一个关键踩坑：WM_LBUTTONDOWN 的 lparam 是客户区坐标

第一版把 `WM_LBUTTONDOWN` 也丢给 `_inside_hit_circle(lparam)` 做命中判断，结果**拖动完全没反应**，
但“点球开面板”一直是好的——这个组合极具迷惑性。

- `_inside_hit_circle` 是为 `WM_NCHITTEST` 写的，那里 lparam 是**屏幕坐标**；
- `WM_LBUTTONDOWN` 的 lparam 却是**客户区坐标**（实测 `l=4194368=0x400040` → x=64,y=64）。

于是“客户区 64,64 减窗口屏幕位置”得到负数，判定在命中圆外 → 不进拖动分支。
而 `WM_LBUTTONUP` 分支没有命中判断，所以只发 UP 也会触发 `_on_click`，把问题掩盖成“一切正常”。

修法：`WM_LBUTTONDOWN` 分支不再调 `_inside_hit_circle`——**消息能到达本窗口就说明命中测试已经放行**，
条件只留 `msg == WM_LBUTTONDOWN and self._draggable`。

教训：DPI/坐标系问题先打印原始 lparam/wparam 和窗口矩形，猜是猜不出来的。

## 遗留

- 拖动只有“左键按住拖”，没有边缘吸附/双击复位。
- 待机球没有右键菜单（托盘里才有），拖到不想要的位置只能再拖回去。
- 面板 idle 位置仍固定右下角，不跟随球（有意为之，见上）。
