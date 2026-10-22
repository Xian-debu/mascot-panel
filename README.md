# mascot — 天选姬桌宠（重构版）

跟随框（聊天面板）+ 环绕球（像素时钟）二合一的 Windows 桌宠。旧实现 `E:\TX-Pet` 冻结保留，本仓库与其零共享代码。
规划与决策记录在 `/root/mascot-admin`。

> **当前状态（2026-10-23）**：M0–M33 已交付，A 阶段（降级放行交互 / 直连 DeepSeek / 状态目录单一真源）完成。
> 2026-10-23 起暂停功能推进，先修用户实测反馈的问题（M34：频闪、分钟星、底栏），并改为"真机自用验收"的工作方式。
> 安装版：`%LOCALAPPDATA%\mascot\app\0.1.0\mascot.exe`；开发副本：`C:/Users/Public/mascot`。

## 它是什么

天选姬（游戏本自带像素宠物）在桌面上走动时，旁边跟随一个聊天面板；点面板时钟图标 → 面板变成像素时钟球绕宠物公转。
宠物没开时，右下角常驻像素时钟球，可拖动、记忆位置、拖到边缘吸附；单击开面板、双击复位。
聊天直连 DeepSeek（key 只读环境变量 `DEEPSEEK_AUTH_TOKEN`，不落盘）。

## 结构

```
src/mascot_core/    纯逻辑（无 Win32）：轨道几何、命中、状态机、配置、设计令牌、provider 契约
src/mascot_win/     Windows 平台层：分层窗口、Win32 调用、单实例、宠物探测
src/mascot_render/  PIL 渲染：像素时钟球、状态灯、提示环
src/mascot_app/     组装与 CLI（run / doctor / ctl / update），web/ 面板前端（HTML/CSS/JS）
scripts/            build-win.sh / install-win.sh / uninstall-win.sh / deploy-win.sh
packaging/          PyInstaller 入口与 spec
```

## 运行

```bash
uv sync --group dev
uv run mascot doctor                  # 环境体检（JSON）
uv run mascot run --provider deepseek # 前台启动（Ctrl+C 退出）
uv run ruff check . && uv run pyright # 静态检查
```

Windows 开发副本（同步源码过去，用那边的 venv 跑）：

```bash
WIN_ROOT=/mnt/c/Users/Public/mascot bash scripts/deploy-win.sh
cd /mnt/c/Users/Public/mascot && ./venv/Scripts/python.exe -m mascot_app run --provider deepseek
```

打包安装（只在阶段性稳定时做，不要每改一行就重建）：

```bash
bash scripts/build-win.sh && bash scripts/install-win.sh
```

## 约定（详见 AGENTS.md）

- 一步一提交，subject `<范围>: <做了什么>`，body 写"为什么 + 实测数字"。
- 颜色/字号/圆角只允许定义在 `mascot_core.tokens`。
- 不硬编码用户路径、盘符、发行版名、端口。
- 行为验证 = 真机自己用（聊天/拖动/看闪不闪），不写一次性验收脚本。
