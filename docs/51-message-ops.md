# B2 · 消息操作（M37）

> 目标：把原版 pet-overlay 的消息操作条追平，并把「上下移动」换成拖动。
> 验收口径仍是「用户能启动、能点、能落盘、重启后还在」。

## 交互（全部在面板消息上）

悬停某条消息 → 右上角出现图标操作条（14px 线性 SVG，tooltip 说明）：

| 图标 | 动作 | 落盘字段 |
| --- | --- | --- |
| 复制 | 复制正文到剪贴板（短暂变亮） | — |
| 折叠 / 展开 | 只显示一行 + 渐隐 | `collapsed` |
| 编辑 | 就地 textarea，保存后旧正文进 `history` | `text`, `history` |
| 冻结 / 解冻 | 这条不发给 AI | `frozen` |
| ↩N | 在历史版本间循环（N 为可回退版本数） | `text`, `history` |
| 六点把手 | **拖动**到任意位置 | 消息数组顺序 |
| 勾选 | 进入多选 | — |

多选态：每条消息左侧出现勾选框，点消息本体切换选中；底部出现选区条「已选 N 条 ·
冻结 · 解冻 · 合并 · 总结 · 取消」。少于 2 条时合并/总结置灰。

- **合并**：全 user 或全 assistant 时纯拼接；混合角色生成一条 assistant，每段加
  `**User:**` / `**Assistant:**` 前缀，插回最小下标。
- **总结**：调 DeepSeek 非流式接口生成摘要，用一条 `**摘要（N 条）：**` 的 assistant 消息
  替换选中项。没连上模型时退化为「（未连接模型，以下为摘录）」，不会丢内容。

## 实现分工

- `src/mascot_core/sessions.py`：纯逻辑 `find_index / toggle_freeze / bulk_freeze /
  toggle_collapse / edit_message / switch_version / move_message / move_to / merge_messages`。
- `src/mascot_core/contract.py`：`Message` 增加 `frozen / collapsed / history`，`to_dict`
  只在非空时输出，`history` 同时给 `versions` 计数。
- `src/mascot_app/runtime.py`：JsApi 暴露 freeze_message / bulk_freeze / collapse_message /
  edit_message / switch_version / move_message / merge_messages / reorder / summarize；
  注入模型上下文前过滤 `frozen`；总结在后台线程跑，`snapshot.summarizing` 供前端显示。
- `web/js/msgops.js`：图标、操作条、编辑框、拖动、多选与选区条；`web/css/messages.css` 配套。
- `web/js/chat.js`：重绘签名包含 frozen/collapsed/versions/选区状态；支持 `**粗体**`。

## 本轮的坑

1. `renderMessages` 里「编辑中不重绘」的闸门把 `refreshMessages(force)` 也挡掉了 →
   一旦进入编辑态，之后所有操作都不刷新。现在 force 参数直达。
2. 编辑框被折叠样式裁成一条线 → 进编辑态移除 `collapsed/folded`，CSS 也放开 `.msg.editing .body`。
3. 窄气泡里两字按钮会竖排 → `.acts/.act{white-space:nowrap}`；图标化后更省宽度。
4. 合并消息里的 `**Role:**` 需要粗体渲染，否则满屏星号 → `buildBody` 增加行内粗体。
5. 点按钮时坐标差 20px 就完全无反应（按钮间隙不吃事件），真机自测要先用截图标注坐标。
6. 改 web 资源后**必须** `deploy-win.sh` + venv `pip install --force-reinstall`，否则
   site-packages 里还是旧 JS（venv 是拷贝安装）。

## 真机验收记录（2026-10-23 19:0x–19:2x，开发副本）

- 冻结/解冻、折叠/展开、编辑、版本循环：落盘正确，重启后保持。
- 拖动：把第一条拖到第二条下方，`sessions.json` 顺序变化，界面即时跟上。
- 多选 3 条 → 合并：生成一条 assistant，三段带角色前缀，位置在最小下标。
- 多选 2 条 → 总结：DeepSeek 返回真实摘要，替换两条，界面显示 `**摘要（2 条）：**`。
- 会话抽屉、发送、B1 功能不回退。

## 还没做

- 选区条按钮在窄窗口下的换行（当前够用）。
- 总结没有「取消」按钮（大模型慢时应能中止）。
- 撤销/重做（合并、总结、删除都不可逆）。
