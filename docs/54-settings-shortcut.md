# M39 / B3 收尾：设置页、开始菜单项与一次数据丢失事故

日期：2026-10-23（用户 m01891 授权「完善 B3 剩余项」）

## 1. 设置页（模型切换 + API Key 录入）

- 入口：面板标题栏齿轮按钮（14px 内联 SVG）。**坑**：`button` 默认 `padding:6px 10px`，22px 宽的按钮内容宽度会被压成 0，SVG 被 flex 缩成一条缝 —— 必须 `padding:0`。
- 浮层内容：模型下拉（`deepseek-chat · 快` / `deepseek-reasoner · 推理`）、API Key 密码框、状态提示、保存。
- 模型：`configfile.set_config_value("provider_model", ...)` 写 `config.toml`，同时 `self.provider.model` 立即生效，无需重启。
- Key：写用户级环境变量 `DEEPSEEK_AUTH_TOKEN`（`winreg` 写 `HKCU\\Environment` + `WM_SETTINGCHANGE` 广播 + 同步本进程 `os.environ`），key 不进 config.toml、不进日志；保存后立刻起线程探一次 provider 健康。
- 语义：key 留空 = 只改模型；已设置时提示「已设置（留空不修改）」。
- 已验证（开发副本）：切 reasoner 落盘并在重启后保持；写入错误 key 后面板立即变红显示「降级 / 后端不可达（HTTP 401）」，说明立即生效；还原真实 key 后重启恢复；reasoner 真发消息有回复。

## 2. 开始菜单项

- `scripts/make-shortcut.ps1`（**纯 ASCII**：PowerShell 5.1 按 ANSI 读脚本，中文注释会解出引号导致语法错误），名字用码点拼 `天选姬`。
- `install-win.sh` 建 `%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\天选姬.lnk`（Target=安装 exe，WorkingDirectory=安装目录，图标取 exe 第 0 号）；`uninstall-win.sh` 用 `-Remove` 删除。
- 顺手清掉上一会话留下的乱码快捷方式（UTF-8 名字被 GBK 误解成 `澶╅€夊К.lnk`）。

## 3. 数据丢失事故（未查明根因，如实记录）

- 现象：2026-10-23 19:42 实测安装版状态目录 `sessions.json` 为「你好」5 条消息；19:45 起该文件与 `sessions.json.bak` 都变成 252 字节的空会话「新的对话」，2 条真实对话（斯托克斯定理问答）丢失，全盘 grep 关键词无残留。
- 已排除：安装版 `config.toml` 仍是 00:53 的旧文件（说明设置页的点击没有落到安装版）；`history.json` 仍是原始 3 条；日志只有 19:40:54 与 19:53:36 两次启动，且**没有**「从 history.json 迁移」记录 —— 启动读到的已经是空会话文件。
- 恢复：把空的 `sessions.json` 归档为 `sessions.json.lost-1953`（`.bak` 同理），重启后由 `history.json` 自动迁移回「你好」3 条消息。
- 防护（已提交 `fcfd0ce`）：`save_session_store` 写盘前轮转三份备份 `.bak / .bak1 / .bak2`，一次坏写不会再抹掉唯一备份。
- 教训：只留一份 `.bak` 等于没有备份 —— 坏写会同时覆盖正本与备份；状态目录里的用户对话比任何功能都重要，任何"顺手清空/重置"的路径都要先归档。

## 4. 待办

- 会话搜索、删除回收站、抽屉分页。
- 数据丢失根因仍未定位（怀疑与多实例/安装覆盖时序有关），后续若再现，先保存 `logs/mascot.log` 与三份备份再排查。
