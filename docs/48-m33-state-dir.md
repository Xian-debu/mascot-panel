# M33（A3）：状态目录单一真源与开发隔离

日期：2026-10-23 00:30 前后。路线：`/root/mascot-admin/docs/14-product-roadmap.md` 阶段 A3。

## 为什么做
- 用户在 `C:\Users\ZYX\AppData\Local\mascot` 里看到我验收留下的假消息与截图（`验收消息-…`、
  `（假后端）收到 15 个字…`、`m5-*.png`），而开发部署副本在 `C:\Users\Public\mascot`；
  「为什么有两份」的根因不是安装逻辑，而是**开发/验收跑起来会直接写用户真实状态目录**。
- 各模块各自解析 `%LOCALAPPDATA%/mascot`（config、runtime、cli、single、logging 五处重复），
  没有统一入口，想隔离只能临时改 `LOCALAPPDATA`（会连带影响其它程序）。

## 改动
- 新增 `src/mascot_core/paths.py`：`state_dir()` 单一真源，优先级
  `MASCOT_STATE_DIR` > `%LOCALAPPDATA%/mascot` > `~/.mascot`（无 LOCALAPPDATA 时，Linux CI 同路径）；
  覆盖值支持 `~` 展开。
- 五个调用点统一改为 `state_dir()`：
  `src/mascot_core/config.py`（`default_config_path`）、`src/mascot_app/runtime.py`（`_state_dir`）、
  `src/mascot_app/cli.py`（`_state_dir`，doctor/ctl 用）、`src/mascot_app/logging_setup.py`（`default_log_dir`）、
  `src/mascot_win/single.py`（pid 文件所在目录）。
- 安装版行为不变（无 `MASCOT_STATE_DIR` 时仍是 `%LOCALAPPDATA%/mascot`）；开发/验收显式写 `MASCOT_STATE_DIR`。
- 单测 `tests/unit/test_paths.py` 4 条：覆盖优先、LOCALAPPDATA 回退、home 回退、`~` 展开。

## 真机验证（win-admin，2026-10-23 00:30）
- `MASCOT_STATE_DIR=C:\Users\Public\mascot-devstate-a3` 启动开发版：该目录出现
  `history.json` / `logs/` / `mascot.pid` / `runtime.json` / `state.json`，`state=tracking`、`provider=deepseek`、`degraded=false`。
- `ctl status`（同一 env）正确读到该实例（pid、tracking、pet=TX Mascot）。
- 用户目录 `C:\Users\ZYX\AppData\Local\mascot`：`history.json` 只剩 3 条真实对话
  （用户「你好」+ 安装版自测「安装版测试：请用一句话介绍你自己」及其回复），验收假消息、`m5-*.png`、残留
  `state.json`/`mascot.pid` 已清；`runtime.json` 里我写入的 `panel_offset`/`panel_pos` 已清空（原文件备份在
  `C:\Users\ZYX\AppData\Local\mascot-backup-20261023-002650`）。
- 安装版重启后 `state=tracking`、`provider=deepseek`、`degraded=false`（key 来自用户级环境变量）。
- Linux 门禁：ruff 0 / pyright 0 / pytest **196 passed, 1 skipped**。

## 坑
- `single.py` 里写 `from mascot_core.paths import paths` 是错的（`paths` 是模块不是符号），要 `from mascot_core import paths`；
  pyright 直接报 `"paths" is unknown import symbol`。
- `%LOCALAPPDATA%` 里那批 `m5-*.png` 是我早期验收直接写到用户目录的截图，已随清理删除（仓库 `evidence/` 有同名件）。
- 清理前先整目录备份到 `%LOCALAPPDATA%\mascot-backup-<时间戳>`，可随时还原。

## 遗留
- 开发部署副本 `C:\Users\Public\mascot` 仍存在（构建/部署用），但它不再写用户状态目录；
  日常验收一律带 `MASCOT_STATE_DIR`（已写进 admin `docs/15-engineering-conventions.md`）。
- 安装版从开始菜单启动的 key 供给靠用户级环境变量（本轮已 `setx`）；设置页录入留到 B3。