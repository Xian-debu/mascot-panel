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
