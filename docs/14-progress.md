# 进度报告（自动维护，供明早阅读）

> 每个里程碑完成后追加一节；每条含"做了什么 / 怎么验证 / 提交号 / 已知缺口"。
> 规划基线：`/root/mascot-admin/docs/10-plan.md`。

## M0 骨架与决策落地 — 完成（2026-10-22 夜）

**做了什么**
- 新仓库 `/root/mascot`：hatchling + src 布局，4 个包 `mascot_core / mascot_win / mascot_render / mascot_app`。
- 依赖锁定：`uv.lock`（33 包），`uv sync --group dev` 一次成功。
- `mascot_core`（零平台依赖，纯逻辑）：
  - `geometry.py`：矩形/屏幕夹取/跟随框/环绕球坐标/角度函数；
  - `hit.py`：命中测试（后登记者优先）；
  - `state.py`：IDLE/TRACKING/ORBITAL/DEGRADED 四状态纯函数状态机 + 降级记忆；
  - `config.py`：pydantic-settings，TOML 与 `MASCOT_*` 环境变量；
  - `contract.py`：`ChatProvider` 协议、`HealthState`；
  - `tokens.py`：HTML/CSS 与 PIL 共用设计 token。
- `mascot_app`：CLI `run/doctor/ctl`，JSON + exit code 契约；WSL/Null 两个 provider；JSON 行日志。
- CI：GitHub Actions，ubuntu + windows 双矩阵，ruff/pyright/pytest/doctor smoke。

**怎么验证（当时命令与输出）**
```
uv run ruff check .        -> All checks passed!
uv run pyright             -> 0 errors, 0 warnings
uv run pytest              -> 34 passed in 0.11s
uv run mascot doctor --offline -> {"ok":true,...} exit=0
uv run mascot doctor       -> provider wsl:down PROVIDER_UNREACHABLE（非 critical）exit=0
uv run mascot ctl status   -> {"ok":true,"data":{"running":false,...}} exit=0
```

**提交**：d3d11d7 init / 9872d14 core / 176c50c app / （CI 与本文档见下一提交）

（缺口已由 M0.5 / M1 关闭）
## M0.5 Windows 侧验证 — 完成（2026-10-22 夜）

**做了什么**
- `scripts/deploy-win.sh` 发布到 `C:/Users/Public/mascot/app/0.1.0`（rsync + MANIFEST.sha256 + current.txt 原子指针）。
- 在该目录建独立 venv（`C:/Users/Public/mascot/venv`，不碰用户全局 Python），`pip install app/0.1.0` 成功。

**怎么验证（Windows Python 3.11.9）**
```
venv/Scripts/python.exe -m mascot_app.cli doctor --offline
-> {"ok":true,...} exit=0
   python 3.11.9 / dependencies all present / state_dir C:\Users\ZYX\AppData\Local\mascot
   platform Windows 10 (AMD64)
```
依赖实际版本：pywebview 6.2.1、pillow 13.0.0、pydantic-settings 2.16.1、psutil 7.2.2。

**提交**：46d2728 deploy 脚本 / 本节见下一提交

**已知缺口**
- 尚未创建任何 GUI 窗口：M1 才开始平台 spike。
- 部署副本与源码可能版本漂移：每次改动后必须重跑 deploy-win.sh（后续 M5 用 PyInstaller 收口）。
## M1 平台 spike — 完成（2026-10-22 夜）

**做了什么**
- `mascot_win/win32.py`：Win32 最小绑定（DPI、枚举、DWM 矩形、互斥体、点击穿透、move/destroy），
  所有句柄显式 argtypes（64 位安全）。
- `mascot_win/layered.py`：`LayeredWindow`（PIL → 预乘 BGRA → UpdateLayeredWindow），支持 alpha 与点击穿透。
- `mascot_win/tracker.py`：`PetTracker`，按进程名/类名找宠物，连续 N 帧丢失才判丢。
- `mascot_win/single.py`：命名互斥体单实例 + 诊断 pid 文件。
- `mascot_render/ball.py`：PIL 画球（呼吸/琥珀等待色）与状态灯。
- `scripts/spike_m1.py`：一次运行验证五个检查点并可截图存证。
- `tests/platform/test_win32.py`：5 条平台测试。

**怎么验证（Windows 侧实跑）**
```
pytest -m platform -> 5 passed in 0.21s
spike_m1.py --seconds 7 ->
  dpi per_monitor_v2 / screen 2560x1600 / dpi 144
  single_instance first=true second=false
  tracker found TX Mascot.exe HwndWrapper[...] rect(1616,272,180,180)
  ball frames=518
  webview alive_s=7.44
  screenshot=evidence/m1-spike.png
```
截图里可以看到：**透明圆角面板 + 青色小球同时浮在浏览器之上**。

**提交**：见 git log（win/render 模块、spike、平台测试、docs/15）

**已知缺口**
- 球是手动线程里的自绘窗口，还没接状态机与面板联动（M2）。
- `mascot ctl stop` 仍是 no-op：IPC 在 M2 一并设计。
- 面板透明区域目前是"整窗透明 + HTML 自绘圆角"，点击穿透策略还没做（M4）。
## M2 运行时联调 — 完成（2026-10-22 夜）

**做了什么**
- `mascot_app/runtime.py`：真进程运行时。状态机副作用 → 面板/小球/横幅；主线程跑 pywebview，
  工作线程"状态机 + 追踪 + 自绘球 + 球消息泵"，交叉只走 `queue.Queue`（D-15 落地）。
- `ctl` 控制面：`status / stop / to-ball / to-panel`，用 `state.json` + `control.json` 两个文件通信，
  `stop` 走 `WM_CLOSE` 让进程正常收尾。
- 面板 HTML 移入包内（`mascot_app/web/panel.html`），由 `js_api` 暴露 `snapshot()/to_ball()`。
- `win32` 补 `find_window / move_window_below / show_window / add_toolwindow / post_close`。
- `scripts/verify_m2.py`：真机端到端验收（起进程→跟随→收球→点球→单实例→停机），退出码 0/5。

**怎么验证（Windows 10、2560×1600 @150%、真实 TX-Pet 运行中）**
```
verify_m2.py -> {ok: true, checks: 6/6}
  follow_tracking  tracking, pet TX Mascot.exe 1616,272 180×180
  ctl_to_ball      orbital
  click_ball_returns  ball_hwnd 29626450 → tracking（真 wndproc 点击路径）
  ctl_status_running  running=true
  single_instance   第二个实例 rc=3 ALREADY_RUNNING
  ctl_stop          method=wm_close，10s 内退出
Linux: ruff 0 / pyright 0 / pytest 37 passed
```
截图：`evidence/m2-panel.png`（面板跟随）、`evidence/m2-ball.png`（收球）、`evidence/m2-degraded.png`（降级横幅）。

**提交**：见 git log（runtime/cli/win32/layered/tracker/single/verify_m2/docs/16）

**已知缺口**
- 面板内容仍是联调占位，不是真聊天流（M4）。
- `ctl stop` 依赖窗口标题找 hwnd；面板被隐藏时退化为 kill（M5 前补 pid 兜底）。
- 球不能拖拽/记忆落点（P1）。
## M3 渲染迁移与快照基线 — 完成（2026-10-22 夜）

**做了什么**
- 设计令牌一份真源落地：`panel.html` 只留 `/*__TOKENS__*/` 占位，`load_panel_html()` 注入
  `tokens.css_variables()`；新增派生变量 `--accent-soft/--accent-line/--amber-soft/--amber-line`
  （`tokens.ALPHA_VARS`）。
- CSS 全部改用 `var(--x)`，并修掉一批“从未定义、靠浏览器 fallback 才没崩”的幽灵变量
  （`--muted`/`--r-chip`/`--motion` → `--text-dim`/`--r-card`/`--base`）。
- `mascot_render/ball.py`：球与状态灯取色全部来自 token；修掉高光用 ImageDraw 直接覆盖导致的
  “球心半透明灰点”，改为独立图层 + `Image.alpha_composite`。
- 快照体系：`mascot_render/gallery.py`（用例表 + 暗底拼图）、`scripts/make_baselines.py`、
  `tests/snapshot/test_render_snapshot.py`，基线 9 张入库。
- 契约测试 `tests/unit/test_token_contract.py`：占位符替换、`var(--x)` 全部已声明、CSS 无写死 hex、
  状态灯 token 名有效。

**怎么验证**
```
Linux:   ruff 0 / pyright 0 / pytest 50 passed
Windows: pytest tests/snapshot -q -> 9 passed（Pillow 13.0.0）
真机:    evidence/m3-panel.png（token 注入后面板正常）、
        evidence/m3-render-gallery.png（呼吸四帧 + 琥珀球 + 四态灯）
```

**提交**：见 git log（render/tests/docs/17）

**已知缺口**
- 字号/间距 token 已进 CSS，但 JS 未消费（M4 拆面板时统一）。
- 球仍是实时相位渲染，没有离散像素帧（P2）。
- 面板整体外观仍靠人眼验收（M5 打包后可做固定尺寸快照）。
