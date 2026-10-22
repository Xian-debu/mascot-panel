# 进度报告（自动维护，供明早阅读）

## 明早先读：2026-10-22 夜间交付总结

**做完了什么**：按 docs/10-plan.md 的 M0→M5 全部推进完毕，产品仓库 /root/mascot
（提交轨迹：仓库骨架 → 纯逻辑层 → CLI/provider → CI/进度 → M0.5 部署 → M1 平台 spike →
M2 运行时 → M3 渲染 → M4 面板与聊天 → M5 打包交付）。管理仓库 /root/mascot-admin
补齐 SG-0001…SG-0009 自授权清单。

**现在能做什么**（Windows 上已装好；路径用正斜杠展示，资源管理器里同样可点开）：
```
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe            # 双击/无参数 = GUI
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe doctor     # 体检
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe ctl status # 看状态
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe ctl stop   # 退出
C:/Users/ZYX/AppData/Local/mascot/rollback.bat                    # 停新版、起旧版
```
注意：**开机自启当前是关闭的**（安装时没加 --autostart），要开：`mascot.exe autostart on`。

**验证过的硬事实**（细节见各里程碑小节与 docs/19-m5-delivery.md）：
- Linux：ruff 0 / pyright 0 / pytest 68 passed；Windows：同套测试 68 passed（1 skip）。
- 真机：跟随真实 TX-Pet 窗口（1616,272 180×180）、面板/环绕球同进程共存、ctl 全动作可用。
- 打包：onedir 单 exe，双击=GUI（无控制台闪窗），带参数=CLI；冻结态面板资源正常。
- 安装/卸载/回滚/双跑/自启 全部逐个跑过并留了截图（evidence/m5-*.png、m4-*.png、m3-*.png）。

**需要你拍板/知情的 3 件事**：
1. **旧目录我加了一个文件** E:/TX-Pet/FROZEN.md（只新增、未改未删）。它来自 docs/10 §10 的要求，
   但和 docs/13 §4“不动旧目录”冲突，已按规则写进 SG-0008；不认可直接删掉即可。
2. **冷启动 4.34 s**，没达到 DoD 的 ≤2 s（pythonnet/clr + pywebview 初始化成本）。不影响可用性，
   优化方案列在 docs/19-m5-delivery.md §8，等你决定要不要为它花时间。
3. **功能三档**：docs/12 的“基线包/提质包/氛围包”还等你选（当时问的三个问题：托盘图标要不要、
   氛围层要不要、聊天框要不要做流式）。M5 之后按你的选择继续。

**已知缺口**：未签名（SmartScreen 可能提示）、无自动更新、旧版本目录不自动回收、
面板立绘仍引用旧项目资源（未迁入本仓库）、无流式输出、消息不落盘。

**仓库位置**：
- 产品：/root/mascot（git，README 有结构与命令）
- 管理：/root/mascot-admin（规划、调研、决策、自授权清单；authorization/self-grants.md 倒序读）
- Windows 安装：%LOCALAPPDATA%/mascot/app/0.1.0/（current.txt 指针 + rollback.bat）
- 旧版（冻结）：E:/TX-Pet/（可双跑、可回滚）

---



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

## M4 面板拆分与真聊天流 — 完成（2026-10-22 深夜）

**做了什么**
- 面板从 919 行单文件拆成 `panel.html` + 4 个 CSS + 5 个 JS（`web/css/*`、`web/js/*`），
  `load_panel_html()` 按顺序拼接并替换三个占位符，运行时仍是自包含单文件（不改 pywebview 加载方式）。
- 真聊天链路：`snapshot()` 带 `messages/sending/provider_detail`；`pywebview.api.send()` 只入队，
  worker 线程 `_drain_sends()` 才真正调 provider；`mascot ctl send --text` 走 `control.json`。
- 消息渲染：相邻同角色合并、今天/昨天/日期分桶、markdown-lite（围栏代码块 + 行内 code + 复制）、
  超 12 行折叠、仅在贴近底部时自动滚动；全程 `textContent`，不碰 `innerHTML`。
- 输入框：1–4 行自适应、localStorage 草稿、IME composition 守卫、Enter 发送 / Shift+Enter 换行、
  发送中禁用；用户气泡乐观回显（同文本判重）。
- 降级矩阵落地：探测失败→红点+横幅；发送失败→保留用户消息 + `PROVIDER_DOWN` 事件；
  历史失败→不降级只记 `provider_detail`；`--provider null` 不降级（刻意离线）。
- `scripts/dev-chat-backend.py`（假后端，仅开发用）+ `scripts/verify_m4.py`（9 项真机验收）。

**怎么验证**
```
Linux:   ruff 0 / pyright 0 / pytest 58 passed
Windows: venv\Scripts\python.exe app/0.1.0/scripts/verify_m4.py --provider-url http://127.0.0.1:8891
         -> 9/9 PASS（跟随、历史、发送、回执、sending 复位、未降级、stop、进程退出）
真机:    evidence/m4-chat.png（历史+两轮问答，时间分桶/左右气泡/单行输入框）
```

**提交**：见 git log（web 拆分 + runtime/cli + tests/contract + docs/18）

**已知缺口**
- 无流式输出（需要新增 Python→JS push 通道，M5 之后按需做）。
- 消息不本地持久化，重启依赖 `provider.history()`。
- 折叠阈值固定 12 行，未按面板高度自适应。
- 键盘焦点管理缺 `Esc` 收球、`↑` 编辑上一条。


## M5 — 交付与双跑（2026-10-22）

**做了什么**
- 打包：PyInstaller onedir（`packaging/entry.py` + `packaging/mascot.spec` + `scripts/build-win.sh`），
  单 exe 双入口：无参数=GUI（`run` + 隐藏控制台），有参数=CLI（doctor/run/ctl/autostart）。
  面板 HTML/CSS/JS 随包进 `_internal/mascot_app/web`，冻结态与开发态同一条读取路径。
- 安装：`scripts/install-win.sh` → `%LOCALAPPDATA%\mascot\app\<ver>` + 原子 `current.txt` +
  生成 `rollback.bat`；覆盖安装前先 `ctl stop`（否则 Windows 锁 dll，rm 报 Input/output error）。
- 卸载：`scripts/uninstall-win.sh` 只删版本目录并摘掉指向它的指针，保留日志/状态；`--all` 才整体删。
- 自启：`mascot autostart on|off|status` 只写 `HKCU\...\Run\Mascot`，默认关闭，安装需显式 `--autostart`。
- 双跑：旧版 `E:\TX-Pet` 加 `FROZEN.md` 冻结；新版独立窗口标题/类名/单实例名，两版可同时跑。
- 修语义 bug：`allow_offline` 之前被理解成"后端挂了也不探测"，导致默认配置永远看不到降级横幅；
  现在无条件探测、如实降级（实测默认 GUI 出横幅）。
- 文档：`docs/19-m5-delivery.md`。

**怎么验证**
```
Linux:   ruff 0 / pyright 0 / pytest 68 passed
Windows: dist/mascot/mascot.exe doctor --offline        -> ok, rc 0
         dist/mascot/mascot.exe run --provider null ... -> 面板正常（冻结态资源可读）
         install-win.sh -> app/0.1.0 + current.txt + rollback.bat
         双击等价（无参数）-> tracking，ctl stop 退出
         autostart status/on/off -> 注册表值正确
         rollback.bat -> 停新版 + 起旧版（旧版再被 stop.pyw 清掉）
         旧版+新版同时跑 -> 互不干扰，新版持续 tracking
         uninstall-win.sh -> 只删版本目录与指针
真机截图: evidence/m5-packaged.png、m5-dualrun.png、m5-new-only.png、m5-degraded-default.png
```

**提交**：见 git log（packaging + scripts + autostart + docs/19）

**已知缺口**
- 冷启动实测 4.34 s，未达 DoD ≤2 s（pythonnet/clr + pywebview 初始化成本）；优化方向见 docs/19 §8。
- 未做代码签名；未做自动更新（升级靠再跑 install-win.sh）。
- 旧版本目录不自动回收（保留回滚能力），后续可加 `mascot gc`。
- 面板立绘/图标资源仍引用旧项目目录，后续需迁入本仓库。

## M6 视觉对齐（2026-10-22 晚，用户反馈后）

- 新增 `src/mascot_render/clock.py`：移植原版像素时钟球（44 格、硬色阶、NEAREST、
  指针/刻度/星光/发光），调色板进 `tokens.PIXEL` / `PIXEL_AMBER`；球径 96→128。
- 修 `--provider null` 被标降级的语义 bug（降级只表达“配了后端但连不上”）。
- 验证：Linux 84 passed / ruff 0 / pyright 0；Windows 84 passed（1 skip）；
  真机环绕态截图 `evidence/m6-orbital.png`；快照 13 个用例。
- 细节与下一步（彗尾、面板美术）见 `docs/20-m6-visual.md`。

### M6b 环绕整帧（2026-10-22 夜）

- `mascot_core.geometry.orbit_layout()`：球径 / 轨道半径 / 整帧窗口三个数可单测；
  `ball_ratio` 语义回到“球半径比例”（与原版 `BALL_RATIO` 一致）。
- 环绕窗口改为以宠物为中心的大方窗，球 + 彗尾同帧绘制（`render_orbit_frame`）。
- 点击穿透用 `WM_NCHITTEST` + 命中圆：球内 `HTCLIENT`，球外 `HTTRANSPARENT`；
  命中判断用自记坐标而不是 `GetWindowRect`（异步移动会拿到旧矩形，平台测试复现过）。
- 窗口尺寸变化走 `SetWindowPos` 而不是缩放位图（保像素边缘）。
- 验证：Linux ruff 0 / pyright 0 / pytest 全绿；Windows 全套全绿；
  真机截图 `evidence/m6b-orbital.png`。细节见 `docs/21-m6b-orbit.md`。

### M6c 面板视觉（2026-10-22 夜）

- 标题栏品牌位：星座风 SVG 时钟头像（移植旧版 pet-clock，点一下收进小球）+ 青→紫渐变标题；
  新增 `--violet` 品牌色（不参与状态语义）。
- 空态：青紫渐变四角星 + 提示；修了 signature 初值撞车导致“首帧空态不渲染”的 bug。
- 面板出现 160ms 上浮淡入，尊重 `prefers-reduced-motion`。
- 真机截图 `evidence/m6c-panel.png`、`evidence/m6c-empty.png`；细节见 `docs/22-m6c-panel.md`。
### M7 托盘（2026-10-22 夜）

- 新增 `src/mascot_win/tray.py`：`Shell_NotifyIconW` + 隐藏 popup 窗口 + 每次右键现构建的菜单
  （显示面板 / 收进小球 / 暂停跟随✓ / 开机自启✓ / 退出）。`win32.py` 补常量与原型，
  并把 `Shell_NotifyIconW`/`ExtractIconW` 声明到 **shell32**（放 user32 会启动即报
  `function 'Shell_NotifyIconW' not found`）。
- 运行时接入：`Runtime.command(name)`（内存命令队列，工作线程消费）、托盘双击=面板/小球互切、
  `_paused` 暂停语义（跳过跟随轮询、动画继续）、tip 随状态刷新、
  开机自启开关只在打包 exe 下写注册表（开发态 no-op）。
- CLI：`ctl` 新增 `pause` / `resume`（走 control.json，与托盘共享同一语义）。
- 验收：`scripts/verify_m7.py` 12 项全过（托盘窗口存在、双击互切、pause/resume、status、stop、退出码 0）；
  证据 `evidence/m7-tray-menu.png`；Linux ruff 0 / pyright 0 / pytest 全绿。
- 细节与坑（菜单阻塞消息泵、验收脚本读到旧 state.json）见 `docs/23-m7-tray.md`。
### M8 冷启动（2026-10-22 夜）

- 新增 `src/mascot_app/boot.py`（T0 + mark/marks，snapshot 输出 `boot` 字段）与
  `scripts/measure_start.py`（清状态 → Popen → 轮询 boot → 记 spawn→面板耗时 → ctl stop）。
- 基线暴露真因：工作线程同步等后端（`_load_history` 2s、每轮 `_poll_provider` 2s、`_drain_sends` 同步发送），
  pet_found 2.1s / state_tracking 4.1s，面板从未出现。
- 重构：后端 I/O 全部移出工作线程，新增 `mascot-history` / `mascot-sender` / `mascot-provider` 三个 daemon 线程；
  工作线程只做状态机、跟随、渲染、消息泵。
- 结果（frozen onedir，3 轮）：spawn→面板可见 **703/705/701 ms**（安装版 868/706/713 ms），此前 4.34 s；
  DoD ≤2 s 达成。降级横幅仍约 2.1s 出现（health 超时在独立线程）。
- 回归：Linux ruff 0 / pyright 0 / pytest 全绿；Windows `verify_m4.py` 9 项 PASS、`verify_m7.py` 12 项全过；
  安装版无参启动截图 `evidence/m8-installed.png`。细节见 `docs/24-m8-startup.md`。
