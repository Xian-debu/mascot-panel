# M36 / B1：本地多会话

2026-10-23。对应 mascot-admin `docs/14-product-roadmap.md` 阶段 B 第 1 步。
用户 m00413 授权：「可以，你可以开工B1了，逐步推进，逐步验证后git提交」。

## 为什么

原来只有一份 `history.json`，所有对话挤在一条时间线上：想开个新话题只能清空（`clear_history`），
清掉就找不回来；跨重启要保留又只能一直往后堆。B1 把对话改成「多会话 + 每会话独立消息列表」，
面板内直接新建/切换/改名/删除，不再依赖后端历史。

## 数据

`sessions.json`（落在状态目录，`paths.state_dir()`）::

    {"version": 1, "current": "s1a1686240b1",
     "sessions": [{"id": "...", "title": "迁移测试：旧会话第一条",
                   "created_at": 1792752632.0, "updated_at": 1792752632.0,
                   "messages": [{"role": "user", "text": "...", "ts": ..., "id": "..."}]}]}

- 单文件、原子写（`write_text` 到临时文件再 replace，见 `runtime.save_session_store`）；
- 每会话消息裁到 `history_limit`（默认 50，与旧行为一致），会话数上限 200，超了丢最久没动的（当前会话永远保留）；
- `title` 为空时用 `DEFAULT_TITLE`（新的对话）；**会话里还没有任何消息**且标题仍是默认值时，第一句话自动取首行前 40 字当标题
  （`title_from` 只看这一刻，之后再发消息不会反复改标题；手动改过名的会话自然也不会被动）。

### 旧数据迁移

启动时 `load_session_store(now)`：`sessions.json` 不存在而 `history.json` 存在 → `from_history()`
把旧消息装进一个会话（标题取第一条用户消息首行），立刻落盘 `sessions.json`。
**旧 `history.json` 不删**：留着当回滚保险；之后所有写入只走 `sessions.json`，它就是唯一真源。

## 代码

- `src/mascot_core/sessions.py`（新，纯逻辑无 IO）：`Session`/`SessionStore` + `parse_store`/`dump_store`/`from_history`/`auto_title`。
  `SessionStore` 方法：`find / current / summaries / create / switch / rename / delete / touch / title_from`。
  `delete` 保证至少留一个会话：删掉最后一个时新建一个空白会话；删掉的若是当前会话，`current()` 会落到最近更新的那条。
- `src/mascot_app/runtime.py`：`_sessions_path` / `load_legacy_history` / `load_session_store` / `save_session_store`；
  `_messages` 属性始终指向当前会话的消息列表（其余代码不用改）；`snapshot()` 增 `sessions`（摘要数组，不含正文）、
  `current_session`、`current_title`；`_persist_sessions` 取代 `_persist_history`；`clear_history` 只清当前会话。
  桥接方法 `new_session / switch_session / rename_session / delete_session`，**聊天进行中一律返回 `{"ok": false, "reason": "BUSY"}`**
  （避免切走后回复落进另一个会话）。
- 面板：`panel.html` 标题栏 `button#sess-toggle`（会话名 + ▾）+ `div#drawer`（＋新会话 / 计数 / 列表）。
  `js/sessions.js` 管抽屉开关、行内改名（Enter 确认 / Esc 取消）、两段式删除（点删除 → 变成「删除/取消」）、
  相对时间（刚刚/N 分钟/N 小时/N 天）；`js/sessions.js` 的 `renderSessions` 用签名去重，1s 轮询不会把用户正在编辑的输入框刷掉。
- CSS：`css/sessions.css`；标题沿用原「天选姬」标题的渐变字（`base.css` 里旧的 `.title` 规则随 M36 删除）。

## 验收（2026-10-23 18:50，开发副本 + win-admin 真机点击）

环境：`C:/Users/Public/mascot` 开发副本，`MASCOT_STATE_DIR=C:/Users/Public/mascot-b1state`，DPT 150%。

| 步骤 | 结果 |
|---|---|
| 预置 3 条消息的旧 `history.json` 启动 | 自动生成 `sessions.json`：1 会话、标题「迁移测试：旧会话第一条」、3 条消息；`state.json` 的 `current_session` / `sessions[0].count=3` 正确 |
| 点标题栏会话名 | 抽屉展开：＋新会话、1 个会话、当前行高亮、行下「3 条 · 18:5x · 第二条用户消息」 |
| 点 ＋新会话 | `sessions.json` 变 2 个会话、`current` 指向新的；面板回到空态、标题「新的对话」 |
| 空会话里发一句话 | 标题自动变「你好呀，这是第二个会话」，会话内 2 条消息 |
| 点「改名」→ 输入「会话甲」→ Enter | `sessions.json` 标题变「会话甲」，重启后仍是 |
| 点另一个会话行 | 标题栏、消息列表整体切过去，抽屉自动收起 |
| 点「删除」→「删除」确认 | 该会话消失，计数变 1 个，当前会话不变 |
| 杀进程重启 | `current` / 标题 / 消息原样恢复，抽屉列表一致 |

## 坑

- `SessionStore.summaries` 排序键里 `float(r["updated_at"] or 0.0)` 触发 pyright 报错；改用 `(updated_at, summary)` 元组排序。
- 会话数裁到 200 时排序键曾写成 `s.sid != current_id`，会把**当前**会话排最前并被 `[-200:]` 丢掉；必须是 `s.sid == current_id`。
- 全仓跑 `ruff format src` 会顺带重排 15 个无关文件（本仓此前只跑 `ruff check`）；只对改动的文件跑 format。
- 面板是 `WS_EX_NOACTIVATE`，win-admin 点击前必须 `wwin focus`，否则 `ENV_NOT_FOREGROUND`；
  非当前会话行的「改名/删除」是 hover 才显示（`.sess-act{opacity:0}`），脚本点击前要先 `winput move` 过去。
- `pyright` 只剩一条既有噪音：`runtime.py` 的 `import webview`（分析环境里没装 pywebview），与本次改动无关。

## 没做 / 下一步

- 会话搜索（C 阶段）、抽屉里只显示最近 N 条（现在全列，超过面板高度靠滚动）。
- 删除没有回收站（跟旧 `clear_history` 一致，先问一次就删）。
- 面板加载时若 `sessions.json` 损坏：`parse_store` 返回空 store，`ensure` 会补一个默认会话，不会崩。
