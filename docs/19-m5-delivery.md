# M5 交付：打包、安装、自启、回滚与双跑

> 日期：2026-10-22；里程碑：M5（交付与双跑）。前置：M0–M4（见 docs/14-progress.md）。
> 实测环境：Windows 10 AMD64，2560×1600 @150%（物理像素），真实 TX-Pet 在运行。

## 1. 交付形态

**一个 exe，两种入口**：

| 启动方式 | 行为 |
| --- | --- |
| 双击 `mascot.exe`（无参数） | 当作 GUI：内部等价 `mascot run`，隐藏控制台窗口 |
| `mascot.exe run/doctor/ctl/autostart ...` | 正常 CLI，stdout 输出 JSON、退出码见 docs/05 |

打包：PyInstaller 6.22.3，**onedir**（`dist/mascot/`，含 `_internal/` 与 WebView2Loader）。
不用 onefile：onefile 每次启动要解包到临时目录，冷启动更慢且更容易被杀软扫描。

`packaging/mascot.spec` 要点：

- `PKG = Path(SPECPATH)` —— SPECPATH 是 spec 自己所在目录（`packaging/`），**不是它的父目录**；
  写成 `Path(SPECPATH).parent` 会让 entry 路径变成 `app/0.1.0/entry.py` 而报 "script not found"。
- `datas=[(REPO/'src/mascot_app/web', 'mascot_app/web')]` 把面板 HTML/CSS/JS 打进 `_internal`；
  运行时仍用 `importlib.resources` 读取，所以开发态与冻结态是同一套代码路径。
- hiddenimports：`clr`/`pythonnet`/`clr_loader`/`webview.platforms.edgechromium`/`webview.platforms.winforms`；
  pyinstaller-hooks-contrib 2026.9 自带 `hook-webview.py`、`hook-clr.py`、`hook-psutil.py`。
- excludes：tkinter/pytest/numpy/PIL.ImageTk/matplotlib（减小体积，避免误收）。
- 产出 `dist/mascot/mascot.exe`（7.6 MB）+ `_internal/`（约 60 MB，主要是 pythonnet 与 WebView2 装载器）。

`scripts/build-win.sh`：先 `deploy-win.sh` 同步到 `C:/Users/Public/mascot/app/<ver>/`，
再在 Windows 副本里跑 PyInstaller。**所有传给 Windows python 的路径必须先 `wslpath -w`**，
否则 WSL 路径 `/mnt/c/...` 会被解释成 `C:\mnt\c\...`（首次构建就这么写错过，已清理）。

## 2. 安装布局（沿用 win-admin 两包模型）

```
%LOCALAPPDATA%\mascot\
  app\0.1.0\           ← 不可变版本目录（mascot.exe + _internal）
  current.txt          ← 唯一指针，内容 "0.1.0"（tmp + rename 原子切换）
  rollback.bat         ← 安装时生成：停新版 + 关自启 + 起旧版
  state.json, logs\    ← 运行期数据（卸载默认保留）
  config.toml          ← 可选，用户手写
```

`scripts/install-win.sh` 行为：

1. 若目标版本目录已在跑 → 先 `ctl stop` 再删（Windows 会锁住正在使用的 dll，直接 rm 报
   `Input/output error`；这是 WSL 下覆盖安装最容易踩的坑）。
2. `cp -r dist/mascot` → `app/<ver>`，写 `MANIFEST` 由 PyInstaller 自带，无需额外清单。
3. `current.txt.tmp` → `current.txt` 原子替换。
4. 生成 `rollback.bat`（见 §4）。
5. `--autostart` 才注册开机自启，默认不动注册表。

`scripts/uninstall-win.sh`：停实例 → 关自启 → 只删 `app/<ver>`；若 `current.txt` 正指向该版本则一并删除指针
（否则 pointer 悬空）；`--all` 才删整个 `%LOCALAPPDATA%\mascot`（含日志/状态）。

LOCALAPPDATA 从 Windows 环境读取（`venv/Scripts/python.exe -c "os.environ[...]"`），仓库里没有硬编码用户名。

## 3. 开机自启

`mascot autostart on|off|status [--exe PATH]` → 只写
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的 `Mascot` 值，命令是带引号的 exe 绝对路径。

- 用户级，不需要管理员权限；卸载 = 删一个值，可审计（`reg query` 可见）。
- **默认关闭**，安装脚本必须显式 `--autostart`；`rollback.bat` 会先 `autostart off`。
- 不接受非 exe 目标（开发态 `python -m` 会明确报错，提示用打包版或 `--exe`）。
- 实测：`status → off`，`on` 后注册表值 = `"C:\Users\ZYX\AppData\Local\mascot\app\0.1.0\mascot.exe"`，
  `off` 返回 `removed: true`，再 `status → off`。

## 4. 回滚

`rollback.bat`（安装时生成，CRLF、ASCII 注释 + `chcp 65001`）：

1. 若新版 exe 存在 → `ctl stop`；
2. `autostart off`；
3. 若 `E:\TX-Pet\scripts\start_frameless.bat` 存在 → `call` 它启动旧版；否则提示手动启动。

**实测**：启动新版（pid 43716，tracking）→ 跑 `rollback.bat` → 新版 `running:false`，
旧版 `TX-Pet-Overlay` 窗口出现（pid 52728）；随后 `E:\TX-Pet\src\stop.pyw` 干净停掉旧版。

> 批处理坑：`\n` 行尾的 .bat 在 `if (...)` 块里会解析错位（"xxx 不是内部或外部命令"），
> 必须 CRLF；heredoc 生成时反斜杠还会翻倍，最后统一 `sed -e 's/\\\\/\\/g' -e 's/$/\r/'` 修正。

## 5. 双跑对照

旧版（`E:\TX-Pet`）原样保留，只加 `FROZEN.md` 声明冻结；新版用独立窗口标题
（`mascot-panel`）、独立窗口类（`mascot_layered_`）、独立单实例名（`Local\Mascot.SingleInstance`），
因此两版可同时运行。

**实测**：旧版 overlay（pid 29224）+ 新版（pid 38384）同时存活，新版 `ctl status` 为 `tracking`；
截图 `evidence/m5-dualrun.png`（同屏两套界面）。停旧版后新版继续 tracking（`evidence/m5-new-only.png`）。

## 6. 验收记录

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 打包体检 | `dist/mascot/mascot.exe doctor --offline` | `{"ok":true}`，python 3.11.9，rc 0 |
| 打包 GUI | `mascot.exe run --provider null --duration 8 --screenshot ...` | tracking TX Mascot.exe，面板绘制正常（冻结态资源可读）→ `evidence/m5-packaged.png` |
| 安装 | `install-win.sh` | 版本目录 + current.txt + rollback.bat 生成成功 |
| 安装后 GUI | 双击等价：`mascot.exe`（无参数） | tracking，面板正常；`ctl stop` 用 WM_CLOSE 退出 |
| 自启 | `autostart status/on/off` | 注册表值正确写入/删除，rc 0 |
| 回滚 | `rollback.bat` | 新版停止 + 旧版启动；旧版可被 `stop.pyw` 清理 |
| 双跑 | 两版同时启动 | 互不干扰，新版仍 tracking |
| 卸载 | `uninstall-win.sh` | 只删版本目录与指针，保留 logs/state；`--all` 删整个目录 |
| 冷启动 | 打包 exe 无参数启动 → state.json 出现 pet | **4.34 s**（DoD 目标 ≤2 s，未达标，见 §8） |
| 降级 | 默认配置（allow_offline=true）后端不可达 | 约 0.0–2.1 s 内进 degraded，面板红点 + 琥珀色横幅 → `evidence/m5-degraded-default.png` |

**顺带修掉的语义 bug**：M4 的 `_poll_provider` 写成"仅在 `allow_offline=False` 时探测"，
导致默认配置下后端挂了也不显示降级（横幅永远不出现）。`allow_offline` 的语义应是
"后端不可用时仍继续工作"，不是"装作没事"。现在无条件探测、无条件如实降级；实测默认 GUI 正常出横幅。

## 7. 目录/工程约定补充

- `packaging/` 只放 PyInstaller 入口与 spec，不参与 `uv` 包安装。
- `scripts/build-win.sh / install-win.sh / uninstall-win.sh` 都是"Windows 侧动作的 WSL 驱动"，可重复执行。
- 版本目录会累积：升级后旧版本目录不会自动删（便于回滚）。需要清理时手动删 `app/<旧版本>`，
  或后续加 `mascot gc`（未做，列入缺口）。

## 8. 已知缺口（明确不做/未达标）

1. **冷启动 4.34 s > DoD 2 s**。主要成本在 pythonnet/clr + pywebview 初始化与 PyInstaller 引导。
   候选优化：先把球显示出来再建面板窗口；延迟 import pythonnet；用 `--windowed` 去掉控制台初始化。
   当前不阻塞交付（双击到可用 4 s 可接受），记入 M5 后待办。
2. **代码签名/杀软白名单**：未签名 exe 在部分机器会被 SmartScreen 拦，需要用户点"仍要运行"。
3. **自动更新**：未做；升级 = 再跑一次 `install-win.sh`（新版本目录 + 改指针）。
4. **旧版本目录回收**：未自动清理（保留回滚能力）。
5. **单用户**：安装在 `%LOCALAPPDATA%`，不支持多用户共享安装。
6. 面板里"天选姬"素材仍来自旧项目目录（网页图标/立绘），后续要迁到本仓库资源目录并加来源说明。

## 9. 复现命令

```bash
# WSL 侧：同步 + 打包 + 安装
cd /root/mascot
WIN_ROOT=/mnt/c/Users/Public/mascot bash scripts/build-win.sh
WIN_ROOT=/mnt/c/Users/Public/mascot bash scripts/install-win.sh --autostart

# Windows 侧
C:\Users\ZYX\AppData\Local\mascot\app\0.1.0\mascot.exe doctor
C:\Users\ZYX\AppData\Local\mascot\app\0.1.0\mascot.exe          # GUI
C:\Users\ZYX\AppData\Local\mascot\app\0.1.0\mascot.exe ctl stop
C:\Users\ZYX\AppData\Local\mascot\rollback.bat                    # 回滚到旧版
```
