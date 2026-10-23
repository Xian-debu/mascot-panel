# 55 · 阶段 C：搜索、导出、失败重试（M40）

C 阶段是"提质"：不改主链路，补日常真正会用的三件事——找得到、拿得出去、发失败了能再来一次。
唯一验收标准仍然是"用户能启动、能用"，没有新增任何测试脚本。

## C1 会话搜索

- 位置：会话抽屉里的搜索框（`#sess-q`），标题或正文都搜。
- 实现：`mascot_core/sessions.py` 的 `SessionStore.search(query, limit=50)`（纯逻辑，无 IO）：
  - 归一化 `" ".join(query.split()).lower()`；空串直接回落 `summaries()`；
  - 先看标题命中，再逐条消息找 `text.lower().find(q)`，命中处用 `_excerpt()` 取前后各 18/32 字做片段（压平换行，首尾加 …）；
  - 结果行 = 会话摘要 + `snippet`，按 `updated_at` 倒序。
- 前端：`sessions.js` 140ms 防抖 + 序号防竞态；结果行优先显示 `snippet`；`paintHint` 显示「N 个结果 / 共 M 个」；空结果插入一条提示行；关闭抽屉清空查询。
- 真机：3 个测试会话里搜「香蕉」得 2 条且片段是高亮句；点结果切换会话并收起抽屉；搜只在正文出现的「三天」得 1 条。

## C2 会话导出 Markdown

- 位置：抽屉头部「导出」按钮，导出**当前会话**。
- 实现：`Runtime.export_session(sid="")` → `session_markdown()` 生成标题 + 导出时间 + 每条 `### 我` / `### 天选姬` 正文；写 `<状态目录>/exports/<slug>-<YYYYmmdd-HHMMSS>.md`（`_slug()` 去掉 Windows 非法字符、取前 30 字）；写完用资源管理器定位到该文件。
- 失败语义：找不到会话 → NOT_FOUND，空会话 → EMPTY，写失败 → WRITE；前端分别给「空会话，没内容可导」「导出失败」。
- 真机：点导出后 `exports/香蕉品种-20261023-201307.md` 生成，内容正确，横幅提示文件名。

## C3 发送失败可重试

- 痛点：断网/401 时面板只有一行错误横幅，用户只能重打一遍。
- 后端：`_drain_sends` 里用户消息先存成局部变量 `sent`，异常分支记 `_failed_text` / `_failed_msg_id`；快照新增 `retry_available`；`retry_send()` 先把那条失败的用户消息从会话里摘掉（避免重试后出现两条一样的），再把它塞回发送队列。
- 前端：横幅改为「文字 + 重试按钮」，按 `文字|retry_available` 的签名缓存重建，点击调 `M.api.retrySend()`。
- 真机（这次的验证手法值得复用）：
  1. 用**错误的 key** 启动开发副本（`$env:DEEPSEEK_AUTH_TOKEN='sk-bad-…'`），发一条消息 → 落到 HTTP 401，横幅出现「重试」；
  2. 打开设置页，用系统剪贴板粘回真实 key（`Set-Clipboard` 读注册表，key 不进任何命令行参数）→ 保存后状态立刻变「跟随中」；
  3. 点横幅「重试」→ 同一进程内重发成功的真实回复，`sessions.json` 里只有一条该用户消息 + 一条回复。
- 坑：thinking 占位符会卡住不消失——`chat.js` 的重绘签名只带了流式文本，`streaming.active` 从 true 变 false 时签名不变，于是永远停在「思考中」。签名里补上 `streaming.active` 才修好。

## 交付

| 提交 | 内容 |
| --- | --- |
| ce456a6 | C1 会话搜索 |
| 91a3d3d | C2 导出 Markdown |
| ea4c425 | C3 失败重试 |

相关前端文件：`js/sessions.js`、`js/ui.js`、`js/state.js`、`js/chat.js`、`css/base.css`、`css/sessions.css`。
