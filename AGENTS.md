# mascot 项目级 Agent 规则

> 叠加在 `~/.dsh/AGENTS.md` 之上；冲突以更严者为准。规划文档在 `/root/mascot-admin`。

## 1. 写入边界

允许写：本仓库、`C:/Users/Public/mascot/`（开发期部署副本）、`~/.mascot/`（用户配置与日志，正式版）、`/tmp/`。

禁止：`E:\TX-Pet`（只读参照）、用户个人目录、系统注册表（除本项目自启项）、卸载任何软件。

## 2. 分层纪律

| 层 | 允许 | 禁止 |
|---|---|---|
| `mascot_core` | 纯函数、dataclass、pydantic | 任何 `ctypes`/`win32`/`webview` 导入 |
| `mascot_win` | Win32/ctypes/webview 宿主 | 业务状态（状态机在 core） |
| `mascot_render` | PIL 绘制 | 读窗口句柄、改状态 |
| `mascot_app` | 组装、CLI、provider | 直接写像素 |

**一个方向：app → win/render/providers → core。** core 不认识任何上层。

## 3. 提交规范

- 一步一提交；subject `<范围>: <做了什么>`（范围：`init|core|win|render|app|web|test|docs|ci|deploy|fix|chore`）。
- body 写**为什么**与**实测数字**（耗时、字节、用例数）。
- 提交前必须跑：`uv run ruff check . && uv run pytest`；涉及 Windows 时另跑平台测试。

## 4. 完成定义（DoD）

- [ ] 代码/文档已提交，工作区干净
- [ ] 有可重跑验证命令，且当场跑过（输出贴进提交 body 或 docs）
- [ ] 新增逻辑有对应测试；测试能独立失败
- [ ] 没有引入新的硬编码路径/端口/发行版名

## 5. 安全的边界

桌宠是用户自己的程序，但仍有两条底线：

1. **不静默失败**：任何降级都要在 UI 上可见 + 日志有 `reason_code`。
2. **agent 通道单向只写**：agent 可以向面板推消息，不能代用户点击 UI；该通道默认关闭。
