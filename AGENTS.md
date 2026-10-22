# mascot 项目级 Agent 规则

> 叠加在 `~/.dsh/AGENTS.md` 之上；冲突以更严者为准。规划/复盘文档在 `/root/mascot-admin`。

## 1. 写入边界

允许写：本仓库、`C:/Users/Public/mascot/`（开发期部署副本）、`%LOCALAPPDATA%/mascot`（用户安装版状态，改动前先备份）、`/tmp/`。

禁止：`E:\TX-Pet`（只读参照）、用户个人目录、系统注册表（除本项目自启项）、卸载任何软件。

## 2. 分层纪律

| 层 | 允许 | 禁止 |
|---|---|---|
| `mascot_core` | 纯函数、dataclass、pydantic | 任何 `ctypes`/`win32`/`webview` 导入 |
| `mascot_win` | Win32/ctypes/webview 宿主 | 业务状态（状态机在 core） |
| `mascot_render` | PIL 绘制 | 读窗口句柄、改状态 |
| `mascot_app` | 组装、CLI、provider | 直接写像素 |

**一个方向：app → win/render/providers → core。** core 不认识任何上层。

## 3. 怎么验证（2026-10-23 重定）

1. **默认：真机自用。** 改完就同步到 Windows 开发副本、启动、自己点/聊/拖，看实际效果；让用户启动验收，而不是我写脚本替他看。
2. **允许的自动化只剩两类**：`ruff`/`pyright` 静态检查；纯算法（角度、时间窗、状态机转移）的少量单测——如果保留的话。
3. **禁止**：每个里程碑写一个 `verify_mN.py`；用脚本断言代替亲眼观察；为一次改动重建 exe。
4. 报告验收时必须写清楚"我实际点了什么、看到什么"，不能只贴 `ok: true`。

## 4. 提交规范

- 一步一提交；subject `<范围>: <做了什么>`（范围：`core|win|render|app|web|docs|deploy|fix|chore`）。
- body 写**为什么**与**实测数字/现象**（用户看到的那一帧、耗时、字节）。
- 提交前：`uv run ruff check . && uv run pyright`。

## 5. 完成定义（DoD）

- [ ] 工作区干净、已提交
- [ ] 我本人在真机上跑过，并记录"看到什么"
- [ ] 用户能用一句话说清怎么启动、怎么退回
- [ ] 没有引入新的硬编码路径/端口/发行版名

## 6. 安全边界

1. **不静默失败**：任何降级都要在 UI 上可见 + 日志有 `reason_code`。
2. **agent 通道单向只写**：agent 可向面板推消息，不能代用户点击 UI；默认关闭。
