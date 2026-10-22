# M15 聊天记录：跨重启保留 + 可清空

## 为什么做

M4 起面板里的消息只活在内存里：`Runtime._messages` 是一份 list，
进程一退（关窗口、换版本、重启）整段对话就没了。进度报告里「消息不落盘（重启即丢历史）」
一直是已知缺口——桌宠是长期挂着的程序，用户第二天回来发现昨天聊的全没了，体验上是"记忆断了"。

M15 把对话落到本地文件，重启自动续上，并给 `ctl` 一个显式清空入口。

## 纯逻辑：src/mascot_core/history.py

不依赖 Windows、不碰文件，纯函数，单测覆盖：

- `parse_history(raw)`：接受 `{"version":1,"messages":[...]}` 或裸数组；
  坏 JSON、坏条目（缺 role/text、ts 不是数字）**一律跳过而不抛**——历史文件坏了不该让程序起不来。
- `dump_history(messages)`：写回 `version + messages`（`Message.to_dict()`）。
- `MAX_TEXT = 4000`：单条超长文本截断，避免历史文件被一整段代码撑爆。
- `merge_history(*groups, limit=50)`：合并内存历史与后端历史。去重身份有两个：
  - 有 `id` 时 `(role, msg_id, -1)`；
  - 否则内容指纹 `(role, text, int(ts))`。
  命中任一即视为同一条；按 ts 排序后取最后 `limit` 条（默认 50，与 `MESSAGE_LIMIT` 一致）。

## 运行时：src/mascot_app/runtime.py

- 文件位置：`%LOCALAPPDATA%/mascot/history.json`，与 `state.json`/`runtime.json` 同目录。
- `load_local_history()` / `save_local_history(messages)`：后者原子写（tmp → replace），
  失败只 warning，不影响聊天。
- `__init__` 里先 `self._messages = load_local_history()`——冷启动立刻有历史可显示；
  后端历史回来后再 `merge_history(history, local, limit=MESSAGE_LIMIT)` 合并，
  所以"离线欢迎语"和本地消息都只出现一次。
- `_persist_history()`：复制消息 → 落盘 → **再 `_write_state()`**。
  这一条是给 `ctl status` 与验收脚本用的：否则磁盘有消息、state.json 还是旧的。
- `_drain_sends` 的 `finally` 末尾调用 `_persist_history()`：无论成功、取消还是异常，
  用户那条消息都已经落盘。
- `clear_history()`：清内存 + `save_local_history([])` + 刷新 state。
- `_poll_control` 新增 `clear_history` 分支；`cli.py` 的 `ctl` 新增 `clear-history`。

## 验收

`scripts/verify_m15.py`，14 项全过：

| 检查 | 说明 |
| --- | --- |
| initial_greeting | 首轮只有离线欢迎语 |
| message_shown | 发「记住这句话-M15」后出现在 state |
| history_file_exists / message_persisted | history.json 存在且含该消息 |
| message_restored / restored_count / no_duplicate_* | 重启后两条消息（欢迎语+用户）各一条，无重复 |
| send2 / append_after_restore | 重启后再发「第二轮-M15」，追加在旧记录后 |
| cleared_in_memory / cleared_on_disk | `ctl clear-history` 后内存与文件都空 |
| not_resurrected | 再重启不会"复活"旧消息 |
| first/second/third_exit_code | 三段实例都正常退出（0） |

截图 `evidence/m15-history.png`：重启后打开面板，昨天那条消息还在，新回复追加在后面。

## 两个坑

1. **验收脚本读到上一轮遗留的 `state.json`**：第一轮 stop 之后 state.json 仍在（内容是 idle +
   第一条消息），第二轮 `spawn()` 后 `wait_for(state == "idle")` 和 `wait_for(MARK in texts)`
   立刻返回**旧快照**，紧接着的 `ctl send` 跑在新实例真正就绪之前——而新实例启动时会删除
   `control.json`（清理幽灵消息，见 runtime 冷启动注释），这条 send 就被清掉了。
   于是只有 `append_after_restore` 失败，其它检查全过（因为恢复链路是好的）。
   修法：加 `start_fresh()`，每轮 spawn 前先删 `state.json`/`control.json`，等 idle 后再 sleep 1s。
2. **`_persist_history` 最初只写 history.json 不写 state.json**：内存与磁盘是对的，
   但 `ctl status` 与验收脚本看不到新消息，表现为"消息没发出去"。落盘后顺手刷新 state 即可。

## 遗留

- 历史只存文本，不含 token/流式半截（取消时保留已收到的部分，标记为 partial-<ts>）。
- 没有容量上限轮转（只按条数 limit=50 合并），超长对话不会无限膨胀，但文件里最多 50 条。
- 清空只清本地；旧后端自己的历史（若后端有）不在 M15 范围内。
