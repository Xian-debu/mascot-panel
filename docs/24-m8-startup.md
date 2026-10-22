# M8 · 冷启动优化（4.34 s → 0.7 s）

> 目标（docs/10-plan.md §6 全局 DoD）：双击 exe 到桌宠可见 ≤ 2 s。M5 实测 4.34 s，本阶段先分段测量、再针对性重构。

## 1. 先测量，别猜

新增两个工具：

| 文件 | 作用 |
| --- | --- |
| `src/mascot_app/boot.py` | 模块导入时记 `T0 = time.monotonic()`；`mark(name)` 记录首次到达的毫秒数；`marks()` 供 `snapshot()` 输出 `boot` 字段 |
| `scripts/measure_start.py` | 冷启动基准：清 state/control → `Popen([exe])` → 轮询 `state.json.boot` → 拿到 `panel_hwnd`+`state_tracking` 记 `panel_visible_spawn_ms` → `ctl stop`；支持 `--exe --runs --timeout` |

埋点位置（都在启动关键路径上）：

```
cli_main       CLI 入口（main() 第一行）
worker_start   mascot-runtime 线程开始
worker_dpi     enable_dpi_awareness() 完成
ball_ready     LayeredWindow（球窗口）建成
tray_ready     TrayIcon 建成
pet_found      第一次匹配到宠物窗口
state_<name>   状态机每次转移（effects 之前）
webview_started webview.start() 的回调被调用
panel_hwnd     找到并接管面板 HWND（注入 exe 图标、工具窗样式）
```

这些数字通过 `mascot ctl status` 或 `state.json` 的 `boot` 字段随时可读——线上排查也用它。

## 2. 第一份基线暴露的真问题

| 里程碑 | 修前 |
| --- | --- |
| worker_start | 32 ms |
| pet_found | 2099 ms |
| state_tracking | 4120 ms |
| panel_hwnd | 从未出现（被降级态掩盖） |

工作线程起来只用 32 ms，但"找到宠物"要 2 s、"进入 tracking"要 4 s，说明**不是初始化慢，是主循环被同步 I/O 堵住**：

1. `_worker` 循环前先调 `_load_history()` —— 后端不可达时要等 HTTP 超时（2 s）才返回，循环才开始跑第一帧；
2. 循环里每轮 `_poll_provider()` 也同步探测 health（又是 2 s 超时），且顺序排在 `_poll_pet()` 之后：即使宠物早就找到，`PET_FOUND` 事件也要等下一轮才被消费；
3. `_drain_sends()` 每轮同步调用 provider.send()，一次网络抖动就把动画卡住。

结论：**工作线程只允许做"本机、无阻塞"的事**；任何可能等网络的动作必须搬走。

## 3. 重构：四线程职责切分

```
主线程        pywebview（WebView2 必须在主线程）—— 面板 UI 与 JS 桥
mascot-runtime  状态机、窗口跟随、球体渲染、消息泵、控制文件轮询（绝不发网络）
mascot-history  启动时拉一次历史（成功/失败都只写状态）
mascot-sender   有消息且在发送中才动，10 ms 轮询队列
mascot-provider 每 5 s 探测一次后端健康；`--provider null` 直接跳过
```

跨线程只通过 `queue.Queue` / 带锁的 list 传事件与文本，UI 线程永不阻塞；工作线程永不发 HTTP。三条 I/O 线程都是 daemon 且异常自吞（写 `_error`/`_provider_detail`），不会拖垮主进程。

## 4. 结果（Windows 10，2560×1600 @150%，frozen onedir，各 3 轮）

dist 构建：

| 里程碑 | 均值 |
| --- | --- |
| cli_main | 67 ms |
| ball_ready | 114 ms |
| tray_ready | 130 ms |
| pet_found / state_tracking | 141 / 146 ms |
| webview_started | ~430 ms |
| panel_hwnd | 510 ms |
| **进程创建 → 面板可见** | **703 / 705 / 701 ms** |

安装版（`%LOCALAPPDATA%\mascot\app\0.1.0\mascot.exe`）：panel_hwnd 526 ms，**spawn → panel 868 / 706 / 713 ms**。

对比 M5 的 4.34 s：**约 6 倍**，且稳定（三轮差 < 5 ms，除首轮磁盘冷读 868 ms）。DoD ≤ 2 s 达成。

## 5. 回归

- ruff / pyright / pytest 全绿（单元测试不依赖线程，仍直接调 `_drain_sends()`/`_load_history()`）。
- `verify_m4.py`（真后端聊天 9 项）PASS；`verify_m7.py`（托盘 12 项）全过。
- `install-win.sh` 安装新构建后无参启动截图 `evidence/m8-installed.png`：面板正常、空态星、跟踪中、输入框与按钮齐备。

## 6. 遗留与后续

- **降级横幅延迟 ~2.1 s**：health 超时仍在 provider 线程里等满 timeout，启动不受影响，但"红点"出现偏慢。后续给 health 单独设短超时（如 800 ms）或先乐观显示、超时再降级。
- **首轮磁盘冷读**：安装后第一次启动 868 ms（其余 706/713），属文件系统缓存冷启动，可接受。
- boot 里程碑会随 snapshot 常驻输出（约 10 个键，几百字节），保留作为线上诊断能力。
- 若以后把 provider 换成常驻本地服务，history/sender/provider 三线程可合并，但"工作线程不碰网络"这条规则建议保留。
