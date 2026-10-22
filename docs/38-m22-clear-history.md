# M22 clear-history 对后端 history 也生效

## 动机

M15 的 `ctl clear-history` 只清本地：`history.json` 清了、内存清了，但**后端 history 还在**。
于是重启后 `_load_history()` 把后端还回来的旧消息重新合并进来——用户眼里的「清空」一秒都没坚持到重启。
progress 里的已知缺口「清空历史仅限本地」就是这个。

M22 的做法：清空时把被清消息的 **id** 记下来（`runtime.json` 的 `cleared_history_ids`），
之后每次从后端取 history 都按 id 过滤。不清后端数据——那属于旧项目的聊天记录，
桌宠没有删除用户对话的权限，只负责「不再显示」。

## 改动

### `src/mascot_core/history.py`（纯逻辑）

```python
def filter_cleared(messages: list[Message], cleared: set[str]) -> list[Message]:
    if not cleared:
        return list(messages)
    return [m for m in messages if not (m.msg_id and m.msg_id in cleared)]
```

没有 id 的消息（纯本地）不在这个集合里，不会被误删；集合为空时返回副本，调用方可放心改。

### `src/mascot_app/runtime.py`（flags 读写 + id 集合）

`cleared_history_ids` 落在 `runtime.json`（和 `ball_pos` 同一个文件），
新增 `CLEARED_IDS_KEY`、`MAX_CLEARED_IDS = 200`、`load_cleared_ids()`（过滤非字符串、空串）、
`save_cleared_ids(ids)`（排序后取最后 200 条写回，无内容时删键）。

- `__init__`：`self._cleared_ids = load_cleared_ids()`；
- `_load_history()`：`provider.history()` 成功后先 `filter_cleared(history, self._cleared_ids)` 再 merge；
- `clear_history()`：清内存前收集 `{m.msg_id for m in self._messages if m.msg_id}`，
  并入 `self._cleared_ids` 后 `save_cleared_ids()`，再清盘。

集合只增不减（重启、再次清空都继续累积），但落盘时只保留 200 条（`MAX_CLEARED_IDS`）。

## 验收（`scripts/verify_m22.py`，Windows 14/14 PASS）

假 legacy 后端 `/api/pet/news` 固定返回两条旧消息，分三轮跑：

| 项 | 断言 |
| --- | --- |
| backend_history_loaded | 启动后面板里有「旧问题甲」「旧回答乙」 |
| roles_from_titles | 标题前缀 `主人:` → user，其余 → assistant |
| clear_sent / cleared_in_memory | `ctl clear-history` 返回 ok，state.messages 变空 |
| cleared_ids_saved | runtime.json 的 `cleared_history_ids` 含 `legacy-1`、`legacy-2` |
| history_file_cleared | history.json 也是空 |
| exit_after_clear / exit_after_restart | 两次停止退出码 0 |
| not_resurrected | **重启后后端仍返回同样两条，面板依旧空** |
| new_item_shown | 后端新增第 3 条，重启后只显示这条新的 |
| old_items_still_hidden | 同时旧两条仍然不显示 |
| instance_alive / stop_ok / exit_code | 全程存活，stop 后退出码 0 |

回归：verify_m13 ~ m21 全部 exit 0；Linux pytest 159 passed / ruff 0 / pyright 0。

## 坑

1. **只清本地等于没清**：后端 history 是「真相源」，本地只是缓存；不清远端就必须记 id 过滤。
2. **不能用内容指纹代替 id**：同一句话用户可能说两次，按内容过滤会误伤新消息；id 是后端给的稳定身份。
3. **没有 id 的消息不能进集合**：纯本地消息（欢迎语、离线回复）没有 id，若用空串占位会把所有无 id 消息一起清掉。

## 遗留

- 后端那边仍留着旧对话（本工具不删用户数据）；换设备/清 runtime.json 后旧消息会再次出现；
- `cleared_history_ids` 上限 200 条，截断按 **id 字典序**（`sorted(ids)[-200:]`）而不是时间序——一次清空几千条时，保留下来的未必是最新清掉的那批；
- 只按 id 过滤，后端若把同一条消息换 id 重发（极少数分页实现会这样），仍会显示。
