# 56 · 会话回收站（C4 / M41）

删会话是不可逆操作，而 2026-10-23 那次数据丢失事故证明"用户对话比任何功能都重要"
（见 `docs/54-settings-shortcut.md` 与管理仓 docs/17 §3.3.1）。所以 C 阶段第一件
该补的就是回收站：**删除只是移走，不是销毁**。

## 数据落在哪

| 文件 | 内容 | 说明 |
| --- | --- | --- |
| `sessions.json` | 当前会话（唯一真源） | 删掉的会话立刻从这里消失 |
| `trash.json` | 回收站条目（含完整消息） | 独立文件，写坏了也不影响主数据 |

回收站最多留 30 个（`MAX_ITEMS`），超了丢最旧的；同一个会话重复删只留一条。
`trash.json` 只做"先写 tmp 再 replace"的原子写，不参与 `sessions.json` 的三代备份轮转
（它本身是低风险存档）。

## 纯逻辑

`src/mascot_core/trash.py`（不碰文件系统、不读时钟）：

- `TrashItem(session, deleted_at)`，`summary()` 只出 id/标题/条数/删除时间（抽屉不传正文）。
- `Trash.add(session, now, limit)` / `find(sid)` / `restore(sid) -> Session | None` / `purge(sid) -> bool` / `summaries()`（最近删的排前面）。
- `parse_trash(raw, now)` / `dump_trash(trash)`：坏 JSON、坏条目一律跳过——回收站坏了不该让桌宠起不来。

## runtime 接线

- `_trash_path()`、`load_trash()`、`save_trash()`；`Runtime.__init__` 里 `self._trash = load_trash(now)`。
- `delete_session()`：先 `self._trash.add(session, now)` 再 `self._store.delete(...)`，然后落盘 `sessions.json` + `trash.json`。
- 新桥：`list_trash()`（只读）、`restore_session(sid)`（塞回 `SessionStore` 并把 current 切过去；忙时 BUSY，已存在 EXISTS）、`purge_session(sid)`。
- 快照新增 `trash_count`。

## 面板

- 抽屉头部多了「回收站」按钮，点一下把列表切到回收站（再点一下切回会话列表）。
- 回收站一行显示「标题 / N 条 · 删除于 时间」；悬停给出「恢复 / 删除」，彻底删除要再点一次「彻底删除」确认。
- 恢复成功后自动切回会话列表并选中该会话。
- 提示行：`回收站 · N 个`；空的时候列表里显示「回收站是空的」。

## 真机验收（开发副本，状态目录 `C:/Users/Public/mascot-c4state`）

1. 预置 2 个会话 → 删掉「回收站测试甲」→ `sessions.json` 只剩乙，`trash.json` 里是甲的**完整消息**。
2. 点「回收站」→ 提示「回收站 · 1 个」，行显示「2 条 · 删除于 20:24」。
3. 点「恢复」→ 弹回会话列表，甲重新出现（2 条消息完好），current 切到甲，`trash.json` 变空。
4. 再删一个 → 回收站里点「删除」→ 出现「彻底删除 / 取消」→ 确认后 `trash.json` 变 `{"version":1,"items":[]}`，列表显示「回收站是空的」。
5. 删掉**最后一个**会话 → 自动补一个空白「新的对话」，甲进回收站；**杀进程重启**后回收站里仍是「1 个 · 回收站测试甲 2 条」——落盘与加载都成立。

## 交付

- 提交 `e796cda`（core+panel）
- 涉及文件：`src/mascot_core/trash.py`（新）、`src/mascot_app/runtime.py`、`web/panel.html`、`web/js/sessions.js`、`web/js/state.js`、`web/css/sessions.css`

## 还没做

- 回收站的"清空"与自动过期（现在只有单条彻底删除 + 30 条上限）。
- 回收站里看不到消息正文（只给条数），要看内容得先恢复。
