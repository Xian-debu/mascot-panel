# 进度报告（自动维护，供明早阅读）

## 明早先读：2026-10-22 夜间交付总结（更新至 M26）

**做完了什么**：按 docs/10-plan.md 推进 M0→M13，产品仓库 /root/mascot
（骨架 → 纯逻辑层 → CLI/provider → CI/进度 → 部署 → M1 平台 spike → M2 运行时 → M3 渲染 →
M4 面板与聊天 → M5 打包交付 → M6a/b/c 视觉对齐（像素时钟球/彗尾/品牌位）→ M7 托盘 →
M8 冷启动 → M9 免打扰与多屏定位 → M10 接上旧聊天后端 → M11 流式增量与停止生成 →
M12 配置写回与开关持久化 → M13 待机形态 → M14 待机球像素时钟化/可拖动/记忆位置 →
M15 聊天记录跨重启保留与清空 → M16 待机球右键菜单/边缘吸附/回到右下角 →
M17 配置写回保留注释与未知键 → M18 版本目录列举/回收与真回滚 → M19 配置热重载 → M20 历史条数可配置 → M21 health 独立短超时 → M22 clear-history 对后端 history 也生效 → M23 就地升级命令 update → M24 面板可拖动与位置记忆 → M25 待机球单击/双击手势 → M26 启动时面板窗口真隐藏）。
管理仓库 /root/mascot-admin 补齐 SG-0001…SG-0018 自授权清单（M13 的 SG-0019、M14 的 SG-0020、M15 的 SG-0021、M16 的 SG-0022、M17 的 SG-0023、M18 的 SG-0024、M19 的 SG-0025、M20 的 SG-0026、M21 的 SG-0027、M22 的 SG-0028、M23 的 SG-0029、M24 的 SG-0030、M25 的 SG-0031、M26 的 SG-0032 见当天提交）。

**现在能做什么**（Windows 上已装好）：
```
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe            # 双击/无参数 = GUI
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe doctor     # 体检
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe ctl status # 看状态（含 boot 分段、dnd、paused）
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe ctl dnd on # 免打扰：不自动弹面板
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe ctl stop   # 退出
C:/Users/ZYX/AppData/Local/mascot/app/0.1.0/mascot.exe update --from <目录|zip>  # 就地升级（自动切 current.txt、回收旧目录）
C:/Users/ZYX/AppData/Local/mascot/rollback.bat                    # 停新版、起旧版
```
右击托盘图标有：显示面板 / 收进小球 / 暂停跟随 / 免打扰 / 开机自启 / 退出；双击托盘=面板与小球互切。
注意：**开机自启当前是关闭的**，要开：`mascot.exe autostart on`（或托盘勾选）。

**验证过的硬事实**：
- Linux：ruff 0 / pyright 0 / pytest 全绿；Windows：全量回归通过；M10 验收 9/9、M11 验收 15/15、
  M12 验收 16/16、M13 验收 10/10、M14 验收 9/9、M15 验收 14/14、M16 验收 7/7、
  M17 验收 12/12、M18 验收 15/15、M19 验收 17/17、M20 验收 16/16、M21 验收 15/15、M22 验收 14/14、M23 验收 26/26、M24 验收 10/10、M25 验收 11/11、M26 验收 7/7 PASS。
- 真机跟随 TX-Pet 窗口（961,459 / 1616,272，随窗口移动）、面板与环绕球同进程共存、ctl 全动作可用、
  托盘菜单与双击互切可用、安装/卸载/回滚/双跑/自启逐个跑过（evidence/m5-*、m6*、m7-*、m8-*、m9 验收输出）。
- 冷启动 **进程创建→面板可见 0.70 s**（安装版 0.71–0.87 s），此前 4.34 s；DoD ≤2 s 已达成（docs/24）。
- 打包：onedir 单 exe，双击=GUI（无控制台闪窗），带参数=CLI；冻结态资源正常。

**需要你拍板/知情的 4 件事**：
1. **旧目录我加了一个文件** E:/TX-Pet/FROZEN.md（只新增、未改未删）。与 docs/13 §4“不动旧目录”冲突，
   已写进 SG-0008；不认可直接删掉即可。
2. **冷启动**已从 4.34 s 优化到 0.70 s（M8）。原“要不要为它花时间”的问题自动解决。
3. **功能三档**（docs/12）：基线包能力已全部落地（阅读/操作分离、消息合并折叠、草稿、IME 安全、
   代码块复制、托盘、自启、状态灯、免打扰、**流式增量渲染 + 停止生成**，M11 补齐）。
   提质包/氛围包（docs/12）尚未开工，等你选。
4. **聊天后端已接通旧契约**（M10）：`provider` 默认 `auto`——先探旧 deepseek-chat-rebuild 的
   /api/pet/{status,news,ask}（SSE），不通再探新契约 /api/pet/{health,history,send}。你把旧后端
   起在 127.0.0.1:8890，面板就能真聊（历史来自 /api/pet/news，回复由 SSE 分片拼接）。
   注意：真旧后端需要 API Key，我今晚只用一个模拟旧后端的假服务验证过（scripts/verify_m10.py 9/9 PASS）。

**已知缺口**：未签名（SmartScreen 可能提示）、无网络自动更新（M23 只支持本地目录/zip 升级）、
旧后端未用真实 API Key 实测、待机球单击开面板有 350ms 双击窗口延迟、
面板拖动后是绝对钉住（不跟随宠物、换分辨率不按比例迁移）、启动时若 WebView2 再 Show 面板需 0.3s 节流纠正。

**仓库位置**：
- 产品：/root/mascot（git；README 有结构与命令）
- 管理：/root/mascot-admin（规划/调研/决策/自授权清单）
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
  DoD ≤2 s 达成。降级横幅当时约 2.1s 出现（health 超时在独立线程；M21 已把无后端降级压到 1.9s）。
- 回归：Linux ruff 0 / pyright 0 / pytest 全绿；Windows `verify_m4.py` 9 项 PASS、`verify_m7.py` 12 项全过；
  安装版无参启动截图 `evidence/m8-installed.png`。细节见 `docs/24-m8-startup.md`。

### M9 免打扰与多显示器（2026-10-22 夜）

- 托盘新增 `免打扰` 勾选项、`ctl dnd on|off`、`snapshot().dnd`；DND = 跳过 `SHOW_PANEL` 副作用
  （不改状态机，手动打开优先），tip 追加"（免打扰）"。
- `win32.work_area(x, y)`：按宠物中心点取所在显示器的 rcWork（排除任务栏）；
  `_place_panel` 不再用主屏尺寸，副屏不再被拽回主屏。
- 验收：`scripts/verify_m9.py` 8 项全过（DND 开关、面板隐藏/恢复、手动优先、stop）；
  Windows 全量 93 passed / 1 skipped；Linux ruff 0 / pyright 0 / pytest 87 passed。
  细节见 `docs/25-m9-dnd.md`。
### M10 接上真实后端（2026-10-22 深夜）

- 现实里没有任何服务实现新契约 `/api/pet/{health,history,send}`；唯一存在的是旧
  `deepseek-chat-rebuild` 的 `/api/pet/{status,news,ask}`（新闻格式 + SSE）。
- 新增 `providers/legacy.py`（翻译层：title 前缀定 role、SSE 分片拼接、`[SESSION:]` 延续会话、
  `engine=missing` 降级）与 `providers/auto.py`（先 legacy 再新契约，选中即记住）。
- `Settings.provider` 默认改 `"auto"`；`ctl status` 补 `provider`/`provider_detail`/`paused`/`dnd`。
- 新增 `scripts/dev-legacy-backend.py`（假旧后端）、`scripts/verify_m10.py`（9 项）。
- 验收：真实 Windows 上 `verify_m10.py` 9/9 PASS（auto 认领 legacy、历史两条、SSE 拼接、未降级、stop）；
  `verify_m7.py` 12 项回归全过；无后端时降级文案为「legacy timed out」；截图
  `evidence/m10-chat.png`、`evidence/m10-degraded.png`。Linux ruff 0 / pyright 0 / pytest 95 passed。
- 遗留：真旧后端未实测（需 API Key）、历史无真实时间戳、无流式增量渲染。细节见 `docs/26-m10-backend.md`。

### M11 流式增量渲染与停止生成（2026-10-22 深夜）

- 背景：M10 之后回复是「整段到达」，真后端一次要 10–60 秒，面板看起来像卡死。
- `ChatProvider` 增加**可选** duck-typed `send_stream(text, on_delta)`；legacy 逐片回调，
  wsl/null 退化整段，auto 必须转发（不转发则 auto 模式永远整段到达）。
- 取消不打断线程：置 `_cancel`，下一次 `_on_delta` 抛 `SendCancelled`，已收部分落成
  `partial-*` 消息保留；`ctl cancel-send` 与面板「停止」两条路径都补齐了 `_poll_control` 分支。
- 修 SSE 分片空格 bug：`strip()` 吃掉词间空格（helloworld），改为只剥一个协议前导空格，
  契约测试锁死 `"hello  world"`。
- 验收：`scripts/verify_m11.py` 15 项全过（增量观察 78–98 次采样、取消保留 17–18/84 字）；
  Windows 全量回归通过；Linux ruff 0 / pyright 0 / pytest 98 passed。
  截图 `evidence/m11-streaming.png`、`evidence/m11-stopped.png`。细节见 `docs/27-m11-streaming.md`。
- 遗留：增量不落盘（崩溃即丢）、取消是「停读」非「停写」、history 仍无真实时间戳。

### M12 配置写回与运行态开关持久化（2026-10-22 深夜）

- 痛点：配置只能读不能写（用户要调 fps / 后端地址只能手写 TOML）；DND 与暂停进程一退就丢
  （docs/25 遗留）。
- 新增 `mascot_core/configfile.py`：`coerce_value` + `Settings(**payload)` 校验后再原子落盘，
  所以未知键、类型错、`fps=999` 都被 rc=2 拒绝且文件不动；CLI 加
  `config path|show|get|set|unset`（`show` 同时给磁盘值与生效值，用于排查环境变量覆盖）。
- 新增 `%LOCALAPPDATA%/mascot/runtime.json`（`{"dnd","paused"}`），`Runtime` 启动时读取、
  托盘与 `ctl` 两条切换路径都写回；读坏/写失败只降级不阻塞启动。
  与 `config.toml` 分开：前者是"上次运行状态"，后者是"用户意图"。
- 验收：`scripts/verify_m12.py` 16 项全过（配置写回/拒绝非法/重启后 dnd+paused 仍为 true）；
  Linux ruff 0 / pyright 0 / pytest 全绿（新增 12 项单测）。细节见 `docs/28-m12-config.md`。
- 遗留：配置只支持扁平键、写回会丢注释、无热重载、窗口位置未持久化。


### M13 待机形态（2026-10-22 深夜）

- 痛点：宠物（游戏）没开时进程活着但屏幕全空——球和面板都不显示，只能靠托盘判断，
  等于“软件没启动”。而“先开桌宠、后开游戏”是最常见的使用顺序。
- 状态机新增第五态 `idle_open`：idle 点球 → 独立面板；`PET_LOST` 从 orbital 回来不再收球；
  `PROVIDER_READY` 恢复白名单加入 idle_open。
- 运行时加 `_idle_anchor`（光标所在**显示器**工作区右下角，留 24px）、`_render_idle_ball`
  （渐变球每秒重渲染走相位），冷启动没宠物也立刻有球。
- 验收：`scripts/verify_m13.py` 10 项全过（真实 WM_LBUTTONUP 点球 → idle_open；面板右下各差 24px）。
  Linux ruff 0 / pyright 0 / pytest 全绿。截图 `evidence/m13-idle.png`、`m13-idle-panel.png`。
  细节见 `docs/29-m13-idle.md`。
- 两个坑：pyright 会被 `and self._ball is not None` 沿循环回边窄化成 None（改局部变量）；
  DPI 下 panel_size 是逻辑尺寸、WebView 窗口是物理尺寸（488×634），锚定前必须量真实窗口；
  验收脚本自己也要 `enable_dpi_awareness()` 否则 work_area 返回逻辑坐标。
- 遗留：待机球仍是渐变球（未换像素时钟）、不可拖动、面板 idle 位置不记忆。


### M14 待机球：像素时钟 + 可拖动 + 位置记忆（2026-10-22 深夜）

- 痛点（M13 遗留三条）：待机球还是 M3 渐变球、与轨道球风格不统一；球钉死右下角不可拖动；
  重启不记忆位置。
- 渲染：`_render_idle_ball` 改用 `render_clock(BALL_SIZE, now_ts=time.time(), stuck=self._degraded)`，
  指针按真实时间走，降级时指针停住，与轨道球完全同款。
- 拖动：`LayeredWindow` 加 `enable_drag/disable_drag`，`WM_LBUTTONDOWN` → `SetCapture`，
  `WM_MOUSEMOVE` 算位移（>3px 才算拖动），`WM_LBUTTONUP` 按是否移动分流到 `on_drag_end` 或 `on_click`。
  在拖动时夹到当前屏工作区内。只有待机球启用（轨道球是动画）。
- 位置记忆：`runtime.json` 加 `ball_pos`，`load_ball_pos`/`save_ball_pos`；`save_flags` 改读-改-写，
  不冲掉其它键；`_idle_anchor` 优先用 `ball_pos`，但必须落在某块屏工作区内才用；面板仍贴右下角。
- 验收：`scripts/verify_m14.py` 9 项全过（真实鼠标注入拖动 → 球移动 -160/-120、state 仍 idle、
  `ball_pos` 落盘、拖完再点仍开面板、重启位置恢复）。`verify_m13.py` 回归 10/10。
  Linux ruff 0 / pyright 0 / pytest 全绿。截图 `evidence/m14-ball-zoom.png`、
  `m14-idle-ball.png`、`m14-dragged.png`。细节见 `docs/30-m14-idle-ball.md`。
- 关键坑：**`WM_LBUTTONDOWN` 的 lparam 是客户区坐标**，`_inside_hit_circle` 却按屏幕坐标解释
  （那是 `WM_NCHITTEST` 的语义），于是拖动分支永不进入；而 `WM_LBUTTONUP` 没命中判断，
  点击开面板一直正常，把问题掩盖成“拖动无效但点击正常”。修法：DOWN 分支不再做命中判断。
- 遗留：拖动无边缘吸附/双击复位；待机球无右键菜单；面板 idle 位置仍不跟随球。
- 交付：`dist/mascot/mascot.exe`（7.7M）重建，`install-win.sh` 已装到
  `C:/Users/ZYX/AppData/Local/mascot/app/0.1.0`（`current.txt=0.1.0`），安装版 `mascot.exe doctor` 体检通过。


### M15 聊天记录：跨重启保留 + 可清空（2026-10-22 深夜）

- 痛点：M4 起消息只在内存，进程一退整段对话消失（progress 已知缺口「消息不落盘」）。
  桌宠是长期常驻的程序，重启丢历史等于"记忆断了"。
- 纯逻辑 `src/mascot_core/history.py`：`parse_history`（接受 version+messages 或裸数组，
  坏输入跳过不抛）、`dump_history`、`merge_history`（按 id 或内容指纹去重、按 ts 排序取尾 50 条）、
  单条文本上限 4000。9 项单测。
- 运行时：历史落 `%LOCALAPPDATA%/mascot/history.json`（原子写）；冷启动先读本地历史，
  后端历史回来再合并（欢迎语/消息都不重复）；`_drain_sends` 的 finally 里落盘；
  新增 `clear_history()` 与 `ctl clear-history`。
- 验收：`scripts/verify_m15.py` 14 项全过（发消息→落盘→重启恢复→继续追加→清空→重启不复活）。
  `verify_m13.py` 10/10、`verify_m14.py` 9/9 回归通过。Linux ruff 0 / pyright 0 / pytest 全绿。
  截图 `evidence/m15-history.png`。细节见 `docs/31-m15-history.md`。
- 关键坑：验收脚本第二轮 `wait_for` 读到上一轮遗留的 state.json 旧快照就提前返回，
  `ctl send` 跑在新实例就绪之前，被新实例启动时"清空 control.json"清掉——只有追加项失败，
  其它全过。修法是每轮 spawn 前删 state/control 再等（`start_fresh()`）。
  产品侧另修：落盘后顺手刷新 state.json，`ctl status` 才看得到新消息。
- 遗留：历史只存文本与最近 50 条，无文件轮转；清空仅本地；后端自身历史不在范围内。
- 交付：`dist/mascot/mascot.exe` 重建，`install-win.sh` 已装到
  `C:/Users/ZYX/AppData/Local/mascot/app/0.1.0`（`current.txt=0.1.0`），安装版 doctor 通过。

### M16 待机球：右键菜单 + 边缘吸附 + 回到右下角（2026-10-22 深夜）

- 痛点：M14 遗留「拖到边缘悬空、无吸附」「待机球无右键菜单」，只能用托盘图标操作。
- 边缘吸附：`_on_ball_drag_end` 按松手点所在屏的 `work_area` 判断，`snap=12`，
  左/上贴 8px、右/下对齐工作区边缘再退 8px；吸附结果立即落盘，重启仍在贴边处。
- 右键菜单：`LayeredWindow.enable_context_menu(builder, on_command)` + `_popup_menu()`
  （`CreatePopupMenu` + `TrackPopupMenu(TPM_RIGHTBUTTON|TPM_RETURNCMD)`，选择以返回值回调）；
  球直接复用托盘菜单的同源构造器 `_build_tray_menu` / 分发器 `_on_tray_command`。
  新增 `CMD_RESET_BALL=1007`「小球回到右下角」；轨道态球把菜单换成空构造器，右键不弹。
- `save_ball_pos` 支持 `None`：复位时从 `runtime.json` 删掉 `ball_pos` 键（而非写假坐标）。
- 验收：`scripts/verify_m16.py` 7 项全过（贴边 x=2424 = 2560-128-8、菜单窗口出现、
  键盘选「回到右下角」回到 2408,1448、`ball_pos` 键被清）。`verify_m13.py` 10/10、
  `verify_m14.py` 9/9、`verify_m15.py` 14/14 回归通过。Linux ruff 0 / pyright 0 / pytest 全绿。
  截图 `evidence/m16-menu.png`、`evidence/m16-edge-snap.png`。细节见 `docs/32-m16-ball-menu.md`。
- 关键坑：弹菜单前必须 `SetForegroundWindow`，否则点空白收不起来；`TPM_RETURNCMD` 已用返回值
  给选择，不能再挂 `WM_COMMAND`（会双触发）。
- 遗留：吸附只在松手时生效（无拖动中橡皮筋）、无双击复位、面板 idle 位置仍不跟随球、菜单无图标。
- 交付：`dist/mascot/mascot.exe` 重建（7996831 字节 / 7.7M，21:18），`install-win.sh` 已装到
  `C:/Users/ZYX/AppData/Local/mascot/app/0.1.0`（7996831 字节，`current.txt=0.1.0`），安装版 doctor 通过。

### M17 配置写回：保留注释、未知键与 [table] 段（2026-10-22 深夜）

- 痛点：`mascot config set` 会把整个 config.toml 重建成模板，手写注释、笔记键、`[table]` 全丢。
- 改法：`mascot_core/configfile.py` 写路径改成按行编辑——只替换/删除目标键所在行，
  保留行内注释与缩进；未知键、空行、`[table]` 段原样保留；新增键插在第一个表头之前
  （否则会被 TOML 当成表内键）；`#` 在字符串里不算注释；文件不存在时才写模板。
- 单测：新增 8 项（保留注释/未知键/表、插表前、重复键折叠、幂等、建模板、unset 保留周边注释、
  字符串内 `#`），pytest 135 passed；ruff 0 / pyright 0。
- 验收：`scripts/verify_m17.py` 12 项全过（临时 `--config` 文件上干，不碰真实配置：
  set 后注释/未知键/表都在且仍是合法 TOML、get 回读 20、非法值 999 被拒且文件字节不变、
  unset 删行但独立注释仍在）。细节见 `docs/33-m17-config-comments.md`。
- 关键坑：新键 append 到文件尾会被算进最后一个 `[table]`，必须插在第一个表头前；
  行尾注释跟着键行走（删键时一起删，避免留下指向不存在键的孤立注释）。
- 遗留：仍无热重载（`config set` 后需重启，CLI 返回 `restart_required: true`）；只支持扁平键；
  改写值时不保留 `1_000` 这类原写法。
- 交付：`dist/mascot/mascot.exe` 重建，`install-win.sh` 已装到
  `C:/Users/ZYX/AppData/Local/mascot/app/0.1.0`（`current.txt=0.1.0`），安装版 doctor 通过。

### M18 已安装版本目录：列举、回收、真回滚（2026-10-22 夜）

- 痛点：安装布局是「一版本一目录 + current.txt」，升级只增不减，每次约 45MB（exe 8MB + _internal）；
  `rollback.bat` 只认「停新版 → 启动 E:/TX-Pet」，明明 app/ 里有上一版却不认。
- 新增 `src/mascot_core/versions.py`（纯逻辑）：`is_version_name` / `version_key`（0.10.0 > 0.9.0）/
  `read_current` / `list_versions`（标 current、统计真实字节）/ `pick_prune`（current 必留，
  keep 是总数）/ `prune_versions`（默认 dry_run，删前核对父目录与版本名，backup/ 不碰）。
- CLI 新增 `mascot versions [--prune --keep N --dry-run --app-dir]`，输出 JSON。
- `scripts/install-win.sh`：装完调用新 exe 的 `versions --prune --keep ${KEEP:-2}` 回收；
  用 `sort -V` + `awk` 找**严格小于 current** 的最新版本写进 rollback.bat——有它就启动它并设自启，
  没有才退回 E:/TX-Pet（降级安装不会「回滚」到更新版）。
- 单测 9 项（test_versions.py：版本名判定、排序、current 标记、缺目录、pick_prune 各分支、
  dry-run 不删、真删留 current、外来目录不动），pytest 144 passed / ruff 0 / pyright 0。
- 验收 `scripts/verify_m18.py` 15/15 PASS（临时 app 目录 + 真实安装目录一致性）。
- 端到端：造 0.0.7/0.0.8/0.0.9 假目录 → `KEEP=2 install-win.sh` 后只剩 0.0.9 与 0.1.0，
  回滚目标 0.0.9；清掉假目录重装 → 回滚目标「无，回滚到 E:/TX-Pet」。
- 坑：dist 里必须是带 versions 子命令的新 exe，否则 prune 静默失败；keep 是总数不是额外数；
  版本排序不能按字典序。细节见 `docs/34-m18-versions.md`。
- 遗留：固定保留 2 个版本（不按磁盘占用回收）；无 `mascot rollback` 子命令；目录大小按遍历统计。
- 交付：build-win.sh + install-win.sh 跑完，安装版 doctor/versions 正常；current.txt=0.1.0。

### M19 配置热重载：改 config.toml 不用重启（2026-10-22 夜）

- 痛点：M17 解决了写回丢注释，但「改完必须重启」还在；桌宠是常驻进程。
- 字段分两类：热字段（fps/poll_interval_ms/orbit_speed/orbit_period_s/ball_ratio/orbit_gap/
  follow_offset/lost_frames/notify_pulse）改完立刻生效；冷字段（panel_size/provider/
  pet_window_class/log_level…）不假装生效，只写进 state.json 的 config.restart_required。
- `mascot_core/config.py`：新增 `HOT_FIELDS` 与纯函数 `merge_hot(old, new) -> (merged, restart)`。
- `runtime.py`：`Runtime(..., config_path=, pinned=)`；主循环每秒比 `(mtime_ns, size)`，
  变了就 load_settings → merge_hot → 换 self.settings；解析失败只 warning 不崩；
  interval/frame_s 挪进循环内；snapshot 新增 settings/config 两段。
- `config set/unset` 返回 `hot` 与真实 `restart_required`（以前恒 true）。
- 单测 5 项（test_hot_reload.py：热字段生效且不就地改旧对象、冷字段报重启、provider 需重启、
  HOT_FIELDS 都存在、返回类型），pytest 149 passed / ruff 0 / pyright 0。
- 验收 `scripts/verify_m19.py` 17/17 PASS；回归 M13–M18 全 exit 0。
- 坑：环境变量 MASCOT_* 会盖住 TOML（`_pinned` 自动排除，验收冷字段改用 log_level）；
  `--provider null` 也是覆盖，不 pin 会每秒假报 provider 需重启；
  interval/frame_s 留在循环外会让热重载变成假象。细节见 `docs/35-m19-hot-reload.md`。
- 遗留：冷字段不自动重建窗口/后端；只监视单一路径（无 include）；reloads 不落盘。
- 交付：build-win.sh + install-win.sh 跑完，安装版 doctor/versions 正常。

### M20 历史条数可配置（2026-10-22 夜）

- 痛点：M15 落盘后上限写死 `MESSAGE_LIMIT = 50`，用户改不了。
- `mascot_core/config.py`：新增 `history_limit: int = Field(default=50, ge=5, le=500)`，并加入 `HOT_FIELDS`。
- `runtime.py`：删掉 `MESSAGE_LIMIT`；`save_local_history(messages, limit=50)` 带 limit；
  snapshot 切片、`provider.history(limit=)`、`merge_history(limit=)`、`_persist_history` 全用
  `self.settings.history_limit`；snapshot.settings 增加 `history_limit`；
  `_maybe_reload_config` 里上限调小时立刻裁内存并落盘；`_persist_history` 写盘前先把内存裁到 limit。
- 验收 `scripts/verify_m20.py` 16/16 PASS（启动 5 条、连发 8 条只留最新 5、热改 10 多留、热改回 5 立刻裁、
  history.json 同步、不重启、exit 0）；回归 M13–M19 全 exit 0。
- 坑：只裁盘不裁内存会「假达标」——放宽上限后旧消息复活（grow_keeps_more 一开始就挂了）；
  热重载裁完必须重新落盘。细节见 `docs/36-m20-history-limit.md`。
- 遗留：上限只管条数不管单条长度（MAX_TEXT=4000）；调大不会回填已裁消息；clear-history 仍只清本地。
- 交付：build-win.sh + install-win.sh 跑完，安装版 doctor/versions 正常。

### M21 health 探测独立短超时（2026-10-22 夜）

- 痛点：M8 遗留「降级横幅延迟」；实测无后端时 **4.29s** 才出降级（`boot.state_degraded=4235ms`），
  因为 `AutoProvider.health()` 串行探两次，都用业务超时 `provider_timeout_s=2.0`。
- `mascot_core/config.py`：新增 `health_timeout_s: float = Field(default=0.8, gt=0.05, le=10.0)`（冷字段）。
- providers：`LegacyProvider`/`WslProvider` 增加 `health_timeout_s`（缺省回落业务超时）；
  `_get(path, timeout=None)` 允许逐次覆盖；`health()` 用短超时，`history/send` 用业务超时；
  `AutoProvider` 透传，`make_provider()` 从 settings 取值；snapshot.settings 暴露 `health_timeout_s`。
- 验收 `scripts/verify_m21.py` 15/15 PASS：无后端 1.91s 降级（阈值 <3.0s）、
  假 legacy 后端 0.27s 判健康且不降级、legacy 成功后不再探 wsl、ctl stop/exit 0；回归 M13–M20 全 exit 0。
- 坑：venv 的 python.exe 是转发器（Popen pid ≠ 桌宠 pid，验收要用 `sys._base_executable`+PYTHONPATH）；
  `ctl stop --provider-url` 会 argparse 失败。细节见 `docs/37-m21-health-timeout.md`。
- 遗留：`health_timeout_s` 是冷字段（改完要重启）；超时是 socket 级，不分 connect/read。
- 交付：build-win.sh + install-win.sh 跑完，安装版 doctor/versions 正常。

### M22 clear-history 对后端 history 也生效（2026-10-22 夜）

- 痛点：M15 的 ctl clear-history 只清本地（history.json + 内存），后端 history 还在，重启后 _load_history() 又把旧消息合并回来——已知缺口「清空历史仅限本地」。
- mascot_core/history.py 新增纯函数 filter_cleared(messages, cleared)（按 id 过滤，无 id 消息不动）；mascot_app/runtime.py 新增 load_cleared_ids()/save_cleared_ids()（落 runtime.json 的 cleared_history_ids，上限 200 条）。
- runtime.py：__init__ 载入集合；_load_history() 从后端取到 history 后先过滤再 merge；clear_history() 把被清消息的 id 并入集合并落盘。集合只增不减；不清远端数据（那是用户对话）。
- 验收 scripts/verify_m22.py 14/14 PASS：假 legacy 后端返回两条旧消息 → 读到 → clear-history → 重启后同一后端仍返回这两条但面板仍空、后端新增第 3 条只显示新的；回归 M13–M21 全 exit 0。
- 坑：只清本地等于没清；按内容指纹过滤会误伤重复发言，必须用 id；无 id 消息不能进集合。
- 遗留：远端仍留旧对话（换设备/删 runtime.json 会再现）；cleared_history_ids 上限 200 条、按字典序截断（非时间序）、无过期。
- 交付：docs/38-m22-clear-history.md；build-win.sh + install-win.sh 已跑。

### M23 就地升级命令 update（2026-10-22 夜）

- 痛点：已知缺口「无自动更新」——升级只能跑 WSL 里的 install-win.sh，普通用户拿到新版本没法自己装。
- 新增 mascot_core/update.py：source_kind（目录必须含 mascot.exe / .zip）、_safe_extract（拒 zip slip）、_locate_exe_root（兼容多套一层目录）、install(source, app_dir, version, keep, dry_run, force)。
- install 顺序：校验版本号 → 同版本无 --force 拒绝 → 复制/解压到 app/.incoming-<v> → 成功后才删旧目录并 rename → 原子写 current.txt → prune_versions 回收旧目录；任何异常清掉半成品。dry-run 只报 target/previous/would_remove。
- cli 新增 update 子命令（--from/--version/--keep/--dry-run/--force/--app-dir）；_infer_version 从目录名或 exe --version 推断；_stop_running_instance 升级前用 ctl 停实例（Windows 锁 exe）。
- 验收 scripts/verify_m23.py 26/26 PASS（临时 app-dir + 假 exe）：目录安装/版本推断/切指针/保留回滚目录/keep=2 回收/dry-run 不动盘/同版本需 --force/zip 多套一层/坏来源退出码 2/无 .incoming 残留。
- 坑：Windows 的 subprocess text=True 用 GBK，中文报错让 json.loads 拿到空 stdout（验收要 encoding=utf-8）；不能先删再装（先装 .incoming 再 rename）；升级前必须停实例。
- 遗留：仍无网络自动更新与签名校验；不支持 MSI；装完不自动拉起。
- 交付：docs/39-m23-update.md；build-win.sh + install-win.sh 已跑。

### M24 面板可拖动与位置记忆（2026-10-22 夜）

- 痛点：面板位置全由程序决定（待机右下角 / 跟随偏移），用户拖不了；计划 P1「跟随框记住拖拽偏移」一直没做。
- 前端：panel.html 标题栏加 `pywebview-drag-region`（pywebview 的拖拽区），base.css 给 .bar 加 grab/grabbing 光标；提示 tooltip「拖动可移动面板」。
- runtime.py：接管 `window.move`（pywebview 6.2.1 的 WinForms move 有 bug，SetWindowPos 把 None 传给 int 参数会抛 ctypes.ArgumentError，拖动时窗口不动）→ `_move_panel_from_js()` 按 DPI 逻辑→物理换算后调 win32.move_window。
- 位置记忆：runtime.json 新键 `panel_pos`（load_panel_pos/save_panel_pos）；_place_panel 先量真实窗口，发现位置与 _last_panel_rect 差 >2px 即视为用户拖动 → _adopt_panel_pos 记下来并停止跟随/贴角（钉住）；`_panel_dirty` + 稳定后写一次盘，避免拖动中每帧写 JSON。
- 复位：托盘/待机球菜单「面板回到默认位置」（CMD_RESET_PANEL=1008）与 ctl reset-panel，清 panel_pos 后立即重摆。
- 验收 scripts/verify_m24.py 10/10 PASS：面板可见、初始无 panel_pos、真实鼠标拖标题栏（2048,942 → 1488,612 一带）、panel_pos 落盘、1.5s 不被摆回、重启后位置恢复（±4px）、ctl reset-panel 回右下角（2560-488-24, 1600-634-24）、panel_pos 清掉、两次退出 0；回归 M13–M16 全 exit 0；pytest 170 passed / ruff 0 / pyright 0。
- 坑：只加拖拽区会看到「拖不动 + 日志里 SetWindowPos ctypes 报错」，必须接管 window.move；拖动中写盘会拖慢拖动。
- 遗留：钉住是绝对坐标（不跟随宠物、换分辨率按 clamped 处理不按比例迁移）；无相对偏移记忆；无双击标题栏还原。
- 交付：docs/40-m24-panel-drag.md、evidence/m24-panel-moved.png；build-win.sh + install-win.sh 已跑，安装版 mascot.exe 8018798 字节（22:07），current.txt=0.1.0，安装版 doctor ok（provider 项 false 属预期，auto 后端未起）、versions 正常。

### M25 待机球单击开面板 / 双击回右下角（2026-10-22 夜）

- 痛点：已知缺口「待机球无双击复位」；双击是比右键菜单少两步的「把球放回去」手势。
- 为什么不用 WM_LBUTTONDBLCLK：它要求窗口类带 CS_DBLCLKS，且系统仍先送一次普通单击消息——会出现「第一次单击已经打开面板，双击再复位」的错误顺序。
- 新增纯逻辑 `src/mascot_core/click.py`：`ClickGate(window_ms=350)`，`click(now)` 第一次挂起、窗口内第二次返回 double；`tick(now)` 超时返回 single；`reset()` 放弃挂起。
- runtime.py：球的 on_click 改为 `_on_ball_click`（非 IDLE 立刻 post CLICK_BALL，行为不变；IDLE 时喂 ClickGate，double 就 `_reset_ball_to_corner()`）；工作线程每轮 tick，single 才 post CLICK_BALL；`_on_ball_drag` 开头 reset（拖动不是点击）；托盘「小球回到右下角」与新方法共用。
- 验收 scripts/verify_m25.py 11/11 PASS：球在角落 → 真鼠标拖到 789,469（ball_pos 落盘）→ 双击回 2408,1448 且 ball_pos 清空、状态仍 idle（面板没开）→ 随后单击正常打开面板（2048,942 488×634）、exit 0；回归 M13/M14/M15/M16/M24 全 ok=true。
- 坑：双击不是一条独立消息，每次点击都要喂 ClickGate；拖动前不 reset 会在松手 350ms 后弹面板；pywebview 的 hidden=True 并没有真的藏窗口（启动时 ws_visible=true），验收不能用 IsWindowVisible 判「面板没打开」。
- 遗留：单击开面板多 350ms 延迟（窗口常量，未做成配置）；轨道球无双击手势；启动时那个 WS_VISIBLE 但画不出内容的面板窗口是否拦点击未验证（留 M26）。
- 交付：docs/41-m25-ball-double-click.md；build-win.sh + install-win.sh 已跑，安装版 mascot.exe 8021164 字节（23:28），current.txt=0.1.0，安装版 doctor ok（provider 项 false 属预期）。

### M26 启动时面板窗口真隐藏（2026-10-22 夜）

- 痛点：M25 验收时探针发现——无宠物启动 6s 后 `mascot-panel` 的 hwnd 存在、`WS_VISIBLE` 为真、rect 2048,942 488×634，只是画不出内容。`create_window(hidden=True)` 并没有真藏住。
- 根因：pywebview 6.2.1 的 hidden 分支是 `Opacity=0 → Show → Hide → Opacity=1`（WebView2 必须先 Show 才初始化），但 WebView2 导航完成后内部还会再 Show 一次。
- 改法两层（`src/mascot_app/runtime.py`）：① `_on_gui_start()` 里若状态机是 `State.IDLE` 就 `win32.show_window(hwnd, False)` 并打 boot 标记 `panel_hidden_at_start`；② 主循环每轮 `_enforce_panel_hidden(now)`（0.3s 节流）在 IDLE 且 `is_visible` 时再藏一次，防 pywebview 后续又 Show。
- 关键坑：判定「该藏」必须用状态机状态，而不是自维护的 `_panel_shown` 布尔——第一版用标志时撞上「状态先记、副作用后跑」的竞态：`state_idle_open:625` 早于 `panel_hidden_at_start:687`，把刚要求显示的面板藏了。改读 `machine.state is State.IDLE` 后消失。
- 验收 `scripts/verify_m26.py` 7 项全 true：`panel_hidden_at_start`（`WS_VISIBLE`=0、`IsWindowVisible`=false）、`panel_ws_visible`=false、`panel_not_blocking_clicks`（`WindowFromPoint(面板中心)` 返回别的窗口）、`stays_hidden`（再等 2s 仍隐藏）、点球 → `idle_open` 且 `panel_shown_ws_visible`=true、`ctl to-ball` → `panel_hidden_again`=true、exit 0。回归 M13/M14/M15/M16/M24/M25 全 exit 0。
- 遗留：面板在 IDLE_OPEN 时仍 topmost（跟随宠物压在上方属设计）；`WS_EX_TOOLWINDOW` 只在首次拿 hwnd 时设（无重建场景）；透明 hack 分支未验证。
- 交付：docs/42-m26-panel-hidden.md；build-win.sh + install-win.sh 已跑，安装版 mascot.exe 8021744 字节（23:34），current.txt=0.1.0，安装版 doctor ok。
