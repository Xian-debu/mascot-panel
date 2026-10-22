# M20 历史条数可配置（history_limit）

## 动机

M15 把聊天记录落了盘，但上限写死 `MESSAGE_LIMIT = 50`（progress 已知缺口）。
M20 把它变成 `Settings.history_limit`（默认 50，范围 5–500），并放进 `HOT_FIELDS`：
改配置不用重启，下次写盘/下次快照就按新上限裁。

## 改动

### `src/mascot_core/config.py`

```python
# 历史
history_limit: int = Field(default=50, ge=5, le=500)
```

并加入 `HOT_FIELDS`（在 `notify_pulse` 之后）。

### `src/mascot_app/runtime.py`

- 删除常量 `MESSAGE_LIMIT = 50`；
- `save_local_history(messages, limit=50)` 增加 `limit` 参数，写 `messages[-limit:]`；
- `snapshot()` 的 `messages` 切片、`_load_history()` 里 `provider.history(limit=)` 与
  `merge_history(limit=)`、`_persist_history()` 全部改用 `self.settings.history_limit`；
- `snapshot()["settings"]` 增加 `history_limit`，`ctl status` 能直接看到当前上限；
- `_maybe_reload_config()`：热重载把上限调小后，内存里的旧消息立刻裁掉并重新落盘；
- `_persist_history()`：写盘前先把内存裁到 limit 以内——
  否则「上限 5 + 连发 100 条」时内存会留 100+ 条（盘上只有 5 条，重启后凭空少一大截，属于隐形内存增长）。

## 验收（`scripts/verify_m20.py`，Windows 16 项全 PASS）

| 项 | 断言 |
| --- | --- |
| boot_limit_5 | 启动读 `history_limit = 5`，state.settings 里是 5 |
| boot_no_reload / sent_all | 启动不重载；连发 8 条 ctl send 都成功 |
| messages_capped / keeps_latest | state.messages 只有 5 条，且是 `M20-4`…`M20-8`（留最新） |
| history_file_capped | history.json 同样只有 5 条 |
| grow_set_ok / grow_applied | `config set history_limit 10` 返回 hot=true，≤8s 生效 |
| grow_keeps_more | 再发一条后 state 里有 6 条（上限放宽真的多留） |
| shrink_set_ok / shrink_applied | 热改回 5，内存与快照立刻只有 5 条 |
| shrink_keeps_latest / shrink_file_capped | 留的是最新 `M20-9`，history.json 也裁到 5 |
| instance_alive / stop_ok / exit_code | 全程不重启，stop 后退出码 0 |

回归：verify_m13 ~ m19 全部 exit 0；Linux pytest 151 passed / ruff 0 / pyright 0。

## 坑

1. **只裁盘不裁内存是假达标**：M15 时代 `_persist_history` 只把切片写盘，内存保留全部消息；
   `history_limit=5` 时连发 8 条，state 里是 5 条但内存 13 条，放宽上限后旧消息「复活」，
   看起来像上限没生效。验收 `grow_keeps_more` 一开始就是被这个坑咬到的。
2. **范围校验交给 pydantic**：`ge=5, le=500`，`config set history_limit 2` 会被 CLI 拒绝（退出码 2），
   运行中的实例不受影响。
3. **热重载裁消息要重新落盘**：只裁内存不写盘的话，磁盘上还是旧条数，重启才对齐。

## 遗留

- 上限只约束「会话消息条数」，不压缩单条长度（单条截断在 `mascot_core/history.py` 的
  `MAX_TEXT = 4000`）；
- `history.json` 仍只保留本地，`clear-history` 不回传后端；
- 上限调大不会回填已经裁掉的消息（盘上就没有了）。