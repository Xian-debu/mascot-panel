# M10 接上真实后端：legacy 适配层 + auto 选路

日期：2026-10-22。前置：M0–M9 已交付（像素时钟球、环绕彗尾、面板品牌位、托盘、免打扰、冷启动 0.7s）。

## 1. 问题：面板契约没有实现者

M4 给面板定的契约是 `/api/pet/{health,history,send}`，但这套端点**世界上只有我们的假后端**
（`scripts/dev-chat-backend.py`）实现。真实存在的后端是旧项目 `deepseek-chat-rebuild` 的
`web/routes_pet.py`，它服务于 ASUS 原生桌宠，契约完全不同：

| 用途 | 新契约（我们） | 旧契约（现实） |
| --- | --- | --- |
| 健康 | `GET /api/pet/health` → `{"ok":true}` | `GET /api/pet/status` → `{"status":"ok","engine":"ready"|"missing"|"error",...}` |
| 历史 | `GET /api/pet/history` → `{"messages":[{role,text,ts,id}]}` | `GET /api/pet/news` → `{"code":202000,"data":[{id,title,description,...}]}`，role 藏在 title 前缀 `主人:`/`天选姬:` 里 |
| 发送 | `POST /api/pet/send {"text"}` → `{"text":"..."}` | `POST /api/pet/ask {"message"}` → `text/event-stream`，`data: ` 分片，末条 `data: [SESSION:<id>]` |

结论：要让用户今晚就能真聊，只能**适配旧契约**，而不是要求旧项目改代码。

## 2. `providers/legacy.py`：翻译层

- `health()` 读 `/api/pet/status`：连不上 → DOWN `PROVIDER_UNREACHABLE`；`status != ok` → DEGRADED
  `PROVIDER_BAD_RESPONSE`；`engine in ("missing","error")` → DEGRADED `PROVIDER_ENGINE_DOWN`
  （后端活着但缺 API Key，这时面板仍可用，只是发不出去）。
- `history()` 读 `/api/pet/news`：title 前缀 `主人:`/`主人：` → user，其余 → assistant；正文取
  `description`；`ts` 用当前时间往前递减（旧接口没有时间戳，只能给出相对顺序）；`msg_id = legacy-<id>`。
- `send()` POST `/api/pet/ask`，逐行读 SSE：`data: [SESSION:<id>]` → 记住会话并结束；`data: [ERROR]` →
  抛 `RuntimeError`（面板显示为发送失败）；其余 `data: ` 片段拼接成一条 assistant 消息。**本版不做流式增量**，
  因为面板协议目前是「一次快照全部消息」，改增量要动前端状态机，收益不足以抵消今晚的风险。
- 会话延续：旧后端的 `ask` 接受 `session_id`，我们把上一次返回的 `[SESSION:<id>]` 带回去，
  这样多轮对话不会断。

## 3. `providers/auto.py`：默认选路

`provider = "auto"` 现在是 `Settings` 默认值。`health()` 先探 legacy（一次 GET，2s 超时），
UP 就用它；否则探新契约；两边都不通时返回 DOWN，但 `detail` 里**同时**带上两边的失败原因：

```
后端不可达（legacy timed out），消息暂时发不出去，其它功能正常
```

选中的后端会记住（`_active`），`history`/`send` 都发给它，避免每条消息重新选路。

### 为什么不是"默认 legacy"

默认 legacy 会在将来新契约上线时退化成"永远连不上"；默认 auto 让两套契约都能用，
并且旧后端一停、新后端一起来，用户无须改配置。代价是探测多一次 GET（~1ms 本机 / 2s 超时上限），
而探测已经在工作线程里、2s 才失败一次，不影响启动（M8 已把后端 I/O 移出 UI 线程）。

## 4. 其他改动

- `providers/__init__.py`：`make_provider` 认识 `auto`/`legacy`/`wsl`/`null`，未知名字仍回落 Null。
- `mascot_core/config.py`：`provider` 默认 `"auto"`。
- `cli.py`：`--provider` choices 加 `auto`/`legacy`；`ctl status` 现在返回 `provider`、`provider_detail`、
  `paused`、`dnd`——之前只能从 `state.json` 猜，验收脚本没法断言。
- `scripts/dev-legacy-backend.py`：假旧后端（stdlib），`serve_in_thread()` 供验收脚本 / 契约测试复用。
- `scripts/verify_m10.py`：自己起假旧后端 → 拉实例 → 断言 auto 认领 legacy、历史两条、SSE 拼接、未降级、
  `ctl stop` 正常退出。

## 5. 验收（真实 Windows，真《天选姬》在跑）

`python app/0.1.0/scripts/verify_m10.py` → 9/9 PASS：

```
panel_follows_pet  TX Mascot.exe 961,459 180x180
provider_is_auto   auto
legacy_history_loaded  ['在吗', '在的~ 刚整理完今天的记录。']
assistant_reply_assembled  （假旧后端）收到15 个字：验收消息-...
not_degraded       tracking
process_exited     0
```

回归：`verify_m7.py` 12 项仍全过；无后端启动 → 降级横幅文案变为
`后端不可达（legacy timed out）...`（见 `evidence/m10-degraded.png`）；
有假旧后端时的聊天截图 `evidence/m10-chat.png`（两轮问答，右侧用户/左侧天选姬）。
Linux：ruff 0 / pyright 0 / pytest 95 passed。

## 6. 遗留

1. **真旧后端没实测**：`deepseek-chat-rebuild` 要 API Key，今晚没启动；适配层只对假后端验证过。
   真后端如果 SSE 有额外字段（如 `data: [DONE]`）我们已兼容，但 `news` 的 role 前缀若变化需要改 `USER_PREFIXES`。
2. 历史消息没有真实时间戳 → 面板按"刚刚/今天"分桶会全部落在同一桶。
3. 无流式渲染：长回答要等完整拼接才出现（SSE 仍然边收边读，只是不增量画）。
4. 旧后端 `news` 分页/数量限制未处理，超过 50 条时只取尾部。

## 7. 复现

```bash
# 只跑假旧后端 + 应用（Windows venv）
python app/0.1.0/scripts/dev-legacy-backend.py --port 8893
python -m mascot_app.cli run --provider-url http://127.0.0.1:8893

# 一键验收
python app/0.1.0/scripts/verify_m10.py
```
