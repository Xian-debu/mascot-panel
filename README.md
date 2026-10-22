# mascot — 天选姬桌宠（重构版）

跟随框（聊天面板）+ 环绕球（像素时钟）二合一的 Windows 桌宠。本仓库是 **2026-10 全面重构**的新产物，
旧实现 `E:\TX-Pet`（483 行单文件壳 + 919 行单文件 SPA，无版本控制）**冻结保留**，本仓库与其零共享代码。

> 规划与决策记录在 `/root/mascot-admin`（管理仓库）。本仓库只承载产品代码。
> 当前阶段：**M3 完成**（渲染迁移与快照基线），下一步 M4（面板拆分 + 聊天流 + 降级 UI）。

## 它是什么

天选姬（游戏本自带像素宠物）在桌面上走动时，旁边跟随一个 340×460 的聊天面板；
点面板上的时钟图标 → 面板变成一颗像素时钟球，绕宠物公转（可拖拽调速，点击回到面板）。

## 结构

```
src/mascot_core/    纯逻辑（无 Win32、可 Ubuntu CI 单测）
  geometry.py         跟随偏移、球轨道、屏幕边界 clamp
  hit.py              命中测试纯函数
  state.py            状态机（idle/tracking/orbital/degraded）+ 原因码
  config.py           pydantic-settings 配置（TOML + 环境变量）
  tokens.py           设计令牌 → CSS 变量 + PIL 调色板（唯一颜色真源）
  contract.py         ChatProvider 协议与 DTO
src/mascot_win/     Windows 平台层（仅 windows-latest 测）
src/mascot_render/  渲染（PIL 画球/状态灯 + 快照画廊）
src/mascot_app/     组装与 CLI（run / doctor / ctl），web/panel.html 面板前端
tests/unit/         纯逻辑单测         tests/snapshot/  像素基线
tests/platform/     Win32 平台测试     tests/contract/  provider 契约
scripts/            deploy-win.sh（发布到 Windows 开发副本）、verify_m2.py、make_baselines.py
```

## 快速开始

```bash
uv sync --group dev
uv run mascot doctor          # 环境体检（JSON）
uv run pytest                 # 纯逻辑 + 快照基线（Linux/Windows 均可）
uv run ruff check . && uv run pyright
```

Windows 侧运行（开发期）：

```bash
scripts/deploy-win.sh         # 同步到 C:/Users/Public/mascot/app/<ver>/ 并冒烟
```

## 依赖（2026-10-22 冻结）

运行期：`pywebview>=6.2,<7`（WebView2 壳）、`pillow>=12`（像素渲染）、`pydantic-settings>=2.4`（配置）、`psutil>=6`（进程探测）。
开发期：`pytest`、`ruff`、`pyright`。锁文件 `uv.lock` 入库。

## 约定

- 一步一提交，subject：`<范围>: <做了什么>`，body 写"为什么 + 实测数字"。
- 纯逻辑必须有单测；平台相关代码必须能在无桌面的 CI 上跳过而不失败。
- 颜色/字号/圆角只允许定义在 `mascot_core.tokens`，HTML 与 PIL 都从它派生（`test_token_contract` 把关）。
- 改了绘制就重跑 `scripts/make_baselines.py` 并提交新基线。
- 不硬编码用户路径、盘符、发行版名、端口。
- 详见 `AGENTS.md`。
