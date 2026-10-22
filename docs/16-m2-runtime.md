# 16 · M2 运行时联调（真进程、真跟随、真收球）

> 阶段：M2（实现已完成并在真机上验收）
> 对应代码：`src/mascot_app/runtime.py`、`src/mascot_app/cli.py`、`src/mascot_win/{win32,layered,tracker,single}.py`
> 验收脚本：`scripts/verify_m2.py`（Windows，退出码 0/5）

## 1. 这一步要解决什么

M1 的 spike 只证明“每种能力单独可用”。M2 把它们接成一个真的产品进程：

- `mascot run` 不再是占位，而是一个常驻进程：跟踪宠物窗口 → 面板跟随 → 收进小球 → 点球回面板 → 后端掉线进降级；
- 状态迁移全部走 M0 就定好的纯状态机（`mascot_core.state.Machine`），运行时只负责“把迁移翻译成副作用”；
- 单实例、ctl 控制、状态落盘（`state.json`）就位，给 M5 的自启动/更新留好接口。

## 2. 线程模型（把 D-15 落地）

| 线程 | 职责 | 约束 |
| --- | --- | --- |
| 主线程 | pywebview / WebView2 消息循环（面板） | 必须独占，M1 实测换线程即崩 |
| `mascot-runtime` | 状态机 + 窗口追踪 + 自绘球窗口 + 球的消息泵 | 只碰 Win32 与自己队列 |
| 计时/演示线程 | `--demo` 与 `--duration` 定时 | 只投事件，不碰窗口 |

交叉只走 `queue.Queue`：JS 侧 200ms 轮询 `window.pywebview.api.snapshot()`，Python 侧从不反向调用 JS。这样面板渲染卡顿不会阻塞状态机，状态机也不会踩 WebView 的线程亲和性。

## 3. 关键实现点

### 3.1 事件 → 副作用

状态机输出 `Transition(state, reason, effects)`，运行时把副作用映射为：

| 副作用 | 实际动作 |
| --- | --- |
| SHOW_PANEL / HIDE_PANEL | 找 `mascot-panel` 窗口，`ShowWindow(SW_SHOWNOACTIVATE)` / `SW_HIDE` |
| SHOW_BALL / HIDE_BALL | 自绘球窗口 show/hide |
| START_FRAMES / STOP_FRAMES | 开/停每帧渲染（球只在 orbital 动） |
| MARK_DEGRADED / CLEAR_DEGRADED | 置降级位，面板显示琥珀横幅 |

每次迁移写一行结构化日志（`{"msg":"state","state":...,"detail":...}`），并原子写 `state.json`，让 `ctl status` 在进程外也能读到一致快照。

### 3.2 跟随与放置

`follow_rect(pet_rect, offset, panel_size, screen)` 是纯函数（M0 已单测）：面板贴宠物窗口右侧固定偏移，超出屏幕自动翻边，并且用 `SetWindowPos(..., SWP_NOACTIVATE|SWP_ASYNCWINDOWPOS)` 移动——不用 `SetWindowPos` 同步版本，避免跨线程移动时互相等对方消息泵而卡死（M1 的教训之一）。

### 3.3 控制面（ctl）

无命名管道、无 socket，只用两个文件（都在 `%LOCALAPPDATA%\mascot\`）：

- `state.json`：进程写、ctl 读（原子替换）；
- `control.json`：ctl 写、进程读后即删。

`ctl stop` 走 `WM_CLOSE`，让 pywebview 正常收尾（球窗口、pid 文件、日志 flush 都能跑到）；直接 `kill` 会留下 pid 文件与半截 state.json。

### 3.4 单实例

命名互斥体 `Local\Mascot.SingleInstance`；第二个实例直接 `exit 3 ALREADY_RUNNING`。pid 文件只是诊断信息，不作为判据（进程崩掉时它一定过期）。

## 4. 真机验收结果

环境：Windows 10、2560×1600 @150%、真实 TX-Pet 运行中；`scripts/verify_m2.py` 全绿（6/6）：

```json
{"ok": true, "checks": [
  {"check": "follow_tracking", "ok": true, "state": "tracking",
   "pet": {"x": 1616, "y": 272, "w": 180, "h": 180, "process": "TX Mascot.exe"}},
  {"check": "ctl_to_ball", "ok": true, "state": "orbital"},
  {"check": "click_ball_returns", "ok": true, "ball_hwnd": 29626450},
  {"check": "ctl_status_running", "ok": true, "state": "tracking"},
  {"check": "single_instance", "ok": true, "rc": 3},
  {"check": "ctl_stop", "ok": true, "method": "wm_close"}
]}
```

截图证据：

- `evidence/m2-panel.png`：面板贴在宠物窗口右侧，显示了跟随目标 `TX Mascot.exe`、矩形 `1616,272 180×180`、运行时长；
- `evidence/m2-ball.png`：收进小球后，96px 青球悬在宠物旁；
- `evidence/m2-degraded.png`：`--provider wsl --no-allow-offline` 时进入 degraded，红色状态点 + 琥珀横幅“后端不可达，消息暂时无法收发（离线可用）”。

## 5. 踩过的坑（都已在代码里注释）

1. `webview.create_window(background_color="#01000000")` → `ValueError: #01000000 is not a valid hex triplet color`：透明只能靠 `transparent=True`，不要传背景色。
2. 忘了 `js_api=JsApi(self)` 时，面板能显示但 JS 永远拿不到 `pywebview.api`，`sync()` 静默失败——表现是“窗口在、数据空”。这是最像“CSS 坏了”的假象。
3. `PetTracker` 命中缓存 hwnd 的分支曾返回 `process=""`，于是面板“跟随目标”一栏空白；补 `get_process_name`。
4. 宠物类名里带每次启动随机的 GUID，所以匹配用“类名子串 + 进程名”，默认进程名 `TX Mascot.exe / TXPet.exe / TX Pets.exe`。

## 6. 复跑方式

```bash
# Linux 侧单测/静态检查
uv run ruff check . && uv run pyright && uv run pytest -q

# 发布到 Windows 开发副本并真机验收
WIN_ROOT=/mnt/c/Users/Public/mascot bash scripts/deploy-win.sh
cd /mnt/c/Users/Public/mascot && ./venv/Scripts/python.exe -m pip install -q --no-deps --force-reinstall app/0.1.0
./venv/Scripts/python.exe app/0.1.0/scripts/verify_m2.py
```

## 7. 已知缺口（交给后续里程碑）

- 面板内容仍是“联调占位卡”，没有真正的聊天流 → M4；
- 球没有拖拽落点记忆，桌面边缘的贴边策略只用 `follow_rect` 的屏幕夹取 → P1；
- `ctl stop` 依赖窗口标题找 hwnd，若面板被 WebView 隐藏则退化为 `kill` → M5 前补 pid 兜底。
