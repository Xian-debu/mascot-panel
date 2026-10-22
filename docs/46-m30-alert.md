# M30 · 新消息到达时小球亮提示环（状态灯）

日期：2026-10-22 夜｜提交：产品（本文件同批）｜授权：admin SG-0036

## 为什么

面板收起（待机球/环绕球）时，后端回了消息用户完全不知道——宠物在桌面上「陪着」，
但没有任何「有新东西」的信号。M30 把小球当状态灯用：只要有一条新的 assistant 消息落进对话，
球外圈亮一圈像素环 2.5 秒。不弹窗、不出声音、不改状态机，用户抬头看一眼就能注意到。

选提示环而不是变色：变色会和「降级/琥珀」语义撞车（`palette_for(stuck)`），
环是叠加信息，降级态下也照样清楚（环跟着琥珀调色板走）。

## 行为

| 触发 | 表现 | 时长 |
|---|---|---|
| assistant 消息落进对话（流式完整回复 / 停止后的部分文本） | 球外圈 28 个像素点围成的亮环 | 2.5s |
| 待机态（`State.IDLE`） | 128px 待机球外圈，`size/2-4` 半径 | 同上，1s 重绘一次，最迟 1s 后消失 |
| 环绕态（`State.ORBITAL`） | 绕轨道飞行的球外圈，`ball_r+8` 半径 | 同上，逐帧重绘 |
| 用户自己的消息 | 不亮环（自己发的不用提醒） | — |
| 降级态 | 环用琥珀家族 `cyan-bright` | 同上 |

环的颜色一律 `cyan-bright`（降级时是琥珀家族的 `cyan-bright`），与球的指针刻度同色系，不引入新色。

## 改法

### 渲染层（纯 PIL，可确定性快照）

- `src/mascot_render/clock.py`：新增 `_draw_alert_ring(img, cx, cy, r, palette)`，28 个 3×3 像素块围一圈（硬边、不抗锯齿，符合像素语言）。
- `render_clock(..., alert: bool = False)`：合成完球后在窗口外圈画环，半径 `max(6.0, size/2 - 4)`（待机球 128px → 半径 60，落在球体与窗口边缘之间）。
- `render_orbit_frame(..., alert: bool = False)`：在球心 `(bx, by)` 画环，半径 `ball_r + 8`（球直径 2×ball_r，环在球外 8px，不会盖住刻度）。
- 环不依赖时间参数，`alert=True` 的渲染是确定性的（单测快照可比）。

### 运行时

- `src/mascot_app/runtime.py`：常量 `ALERT_S = 2.5`；`self._alert_until: float`（monotonic 截止时刻）；
  `_mark_alert()` 在消息追加后调用（`_drain_sends` 的完整回复分支与「停止后的部分文本」分支各一次）；
  `_alert_active()` 判当前是否还在窗口内。
- `_render_idle_ball()` / `_render_frame()` 都传 `alert=self._alert_active()`。
- `snapshot()` 增加只读字段 `"alert": bool`（state.json 每秒刷新，`ctl status` 与验收脚本可见）。
- 状态机完全不动：提示环不产生事件、不改状态、不落盘；退出/切态自然消失。

## 验收

`scripts/verify_m30.py`（9 项，Windows 实机）：起假聊天后端（`dev-chat-backend.py`，随机端口）→ 无宠物启动进 `idle`：

| # | 检查 | 实测 |
|---|---|---|
| 1 | `state_idle` | idle |
| 2 | `alert_false_before` | False |
| 3 | `ctl_send_accepted` | ok |
| 4 | `reply_arrived`（假后端回复进了消息列表） | （假后端）收到 15 个字 |
| 5 | `alert_true_after_reply` | True |
| 6 | `screenshot_saved` | evidence/m30-alert.png |
| 7 | `alert_cleared`（≤8s 内回落） | False |
| 8 | `still_idle_after_alert` | idle |
| 9 | `exit_code` | 0 |

结果 `RESULT: PASS`、exit 0。截图 `evidence/m30-alert.png`（全屏，右下角待机球带提示环），
裁切对照 `m30-alert` 里环在球外圈、与刻度不重叠。

单测（Linux，`tests/unit/test_clock.py` 追加 3 项）：

- `test_alert_ring_adds_pixels_outside_ball`：不透明像素 +40 以上，且外接矩形比不带环时更靠边。
- `test_alert_ring_is_deterministic`：同输入两次渲染逐像素相同。
- `test_orbit_frame_alert_adds_ring_around_ball`：环绕帧带环时像素数增加。

回归：`verify_m13/m24/m25/m26/m27/m28/m29/m30` 全 exit 0；ruff 0 / pyright 0 / pytest 全绿。

## 坑

1. **环半径不能贴着球体**：第一版用 `sprite.width/2 + 2`，而球的刻度本身就在球边缘，环和刻度混在一起，截图里几乎看不出来。改成窗口半径 `size/2 - 4` 后才有「球外一圈」的观感。
2. **待机球是 1s 重绘一次，不是逐帧**：环的出现/消失最多晚 1s；验收要留 ≥1s 余量，不能用「发送后 200ms 断言」。
3. **`state.json` 每秒写一次**：`alert` 窗口 2.5s 只覆盖 2–3 次快照，读取必须轮询（0.05s 间隔），固定 sleep 容易读到上一份。
4. **验收脚本把截图存在部署目录**：`ROOT/evidence` 在 `C:\Users\Public\mascot\app\0.1.0`，重新 deploy 会被覆盖；归档要复制回仓库 `evidence/`。
5. **不要改成「new message 才提醒」靠轮询 history**：消息追加本来就在 `_drain_sends` 里，直接在那里打时间戳最省事，也不会重复提醒。

## 遗留

- 提示环只对运行中的实例生效，历史加载（启动时拉到的旧消息）不亮环。
- 环是固定亮度，不做呼吸/闪烁；如果用户觉得不够醒目，再加速度或闪烁参数（会牺牲确定性快照，需要先加 `now_ts` 注入）。
- 面板打开时也会亮环（用户已经看得见消息），暂未按「面板可见性」抑制——多一个判断、收益不大。
