# M29 环绕球双击暂停/恢复公转

## 动机

plan §8 P1「环绕球双击暂停/恢复公转（交互最小侵入）」。环绕球一直匀速绕宠物转，
用户想停下来读时钟、或者不想球一直动时，只能把面板调出来（球就消失了）。
双击是最小侵入的手势：不新增 UI、不占托盘菜单，与 M25 待机球的双击语义（同一颗球，双击=一种"重置/停"）也一致。

单击语义保持 M3：环绕态单击回到面板。双击则停在原地，再双击继续转。

## 行为

| 状态 | 单击 | 双击 |
| --- | --- | --- |
| 待机（无宠物，右下角球） | 打开面板 | 球回到右下角（M25） |
| 环绕态（球绕宠物公转） | 回到面板 | 暂停 / 恢复公转（M29） |
| 跟随中 | 打开面板 | 无（两次单击 = 开/关面板） |

- 暂停时**角度冻结**：球停在原位不动，球里的像素时钟数字继续走（时间是 `render_orbit_frame` 每帧自己读的）。
- 恢复时**从同一角度接着转**：内部做法是 `_orbit_t0 = now - _orbit_frozen_t`，不重新从 0 角度开始，避免球瞬移。
- 离开环绕态（回面板 / 宠物消失）后再进环绕，公转恢复为转动状态（每次进入都是新的轨道起点）。
- `click_window_ms = 0`（M28 关掉双击手势）时，环绕态双击退化为两次单击：第一次就回面板。

## 改法

`src/mascot_app/runtime.py`：

- 新字段 `_orbit_paused` / `_orbit_frozen_t`；`START_FRAMES`（进入环绕态）时重置为转动；
- `_on_ball_click()` 分状态处理：`ORBITAL` 走 `ClickGate`——`DOUBLE → _toggle_orbit_pause()`、`SINGLE → post(CLICK_BALL)`；其余非 IDLE 状态仍立即开面板；
- 新方法 `_toggle_orbit_pause()`：暂停时记 `now - _orbit_t0`，恢复时用它反推新的 `_orbit_t0`，打 `orbit_pause` 日志并刷新 state；
- 主循环渲染帧时 `frame_t = _orbit_frozen_t if _orbit_paused else now - _orbit_t0`；
- 新增 `_ball_circle`（球当前命中圆的**屏幕坐标**，环绕帧每帧更新、待机帧清空）并在 `snapshot()` 里暴露为 `ball_circle`，同时暴露 `orbit_paused`。这两项是为"验收/排障能观测到球此刻在哪、是否暂停"而加的，纯读。

## 验收（`scripts/verify_m29.py`）

还是用 ctypes 假宠物窗口（类名 `MascotFakePet`）进 tracking，再 `ctl to-ball` 进环绕态。
难点是**点中一颗正在移动的球**：

- 球心从 `state.json` 的 `ball_circle` 读，但状态文件每秒才写一次，默认 `orbit_speed=1.0` 时 1 秒球走 100+px，早就飞出命中圆；
- 所以验收先把 `orbit_speed` 配成 **0.05**（用户配置、热重载生效），球 10px/s，1s 前的球心与真实球心相差 < 12px，命中圆半径 ~146px，稳中；
- 采样也用轮询（`wait_move`，0.15s 一次，超时 4s）而不是固定 sleep，因为状态文件 1s 才刷新一次。

Windows 实测（全 true，exit 0）：

| 项 | 实测 |
| --- | --- |
| `state_tracking` / `state_orbital` | true / true |
| `ball_circle` | `[932, 429, 146]` |
| `moved_before` | 10（0.05 速度下 1s 的位移，>3 即视为在动） |
| 双击后 `orbit_paused` / `still_orbital` | true / true（双击没有顺手打开面板） |
| `moved_while_paused` / `frozen_while_paused` | 0 / true |
| `orbit_resumed` / `moved_after_resume` | true / 9 |
| `single_click_returns_panel` | true（有宠物时是 tracking） |
| `exit_code` | 0 |

回归：`verify_m13/m24/m25/m26/m27/m28` 全 exit 0、`ok: true`；Linux ruff 0 / pyright 0 / pytest 全绿。

## 坑

1. **状态文件 1s 写一次决定了验收节奏**：任何"球在不在动"的断言都不能用固定短 sleep 取样，必须轮询到位移超过阈值。第一版 `moved_after_resume` 读到 0 就是这个坑。
2. **命中圆是屏幕坐标**：`_ball_circle` 存的是"窗口左上角 + 窗口内球心"，验收直接拿去 `set_cursor_pos` 才对；存窗口坐标会在多屏/负坐标下点偏。
3. **一次点击可能被 `ClickGate` 吃掉**：双击判定窗口内第一击必须挂起；要是环绕态还保留 M25 前"单击立即开面板"的老路径，双击永远进不了 DOUBLE 分支。
4. **恢复不能重置角度**：直接 `_orbit_t0 = now` 会让球从轨道 0° 开始，视觉上跳到远处。

## 遗留

- 暂停没有任何视觉提示（只有"球不动"这一件事），球里的时钟仍在走——是否加一个"暂停"角标待定。
- 暂停状态不落盘：退出/重启后不记忆（环绕态本身也不跨重启）。
- 托盘菜单/ctl 没有对应的"暂停公转"命令，只有双击手势。
