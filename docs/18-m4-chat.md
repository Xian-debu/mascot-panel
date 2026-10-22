# M4 — 面板拆分、真聊天流与降级 UI

> 目标：把 919 行单文件 SPA 的做法彻底换掉——面板拆成可维护的模块，聊天走真 provider，
> 后端挂了要**体面降级**而不是白屏或崩。

## 1. 面板为什么按文件拆、又为什么不打包

旧实现把 HTML/CSS/JS 全塞在一个 919 行文件里，改一处颜色要跨 600 行找。现在开发态是多个小文件：

```
src/mascot_app/web/
  panel.html        只留结构 + 三个占位符
  css/base.css      重置、面板外框、头部、横幅、页脚、按钮
  css/stream.css    消息流、时间分桶、代码块/折叠
  css/composer.css  输入框 1–4 行自适应
  css/states.css    状态灯动画（idle/breathe、working/pulse、awaiting/slow、error）
  js/state.js       M.store / M.api / 轮询
  js/ui.js          paintShell：状态灯、标题芯片、降级横幅
  js/chat.js        renderMessages：分桶、合并同角色、markdown-lite、折叠、复制
  js/composer.js    initComposer：自适应高度、草稿、IME、Enter 发送
  js/main.js        boot + apply(snapshot) + 乐观回显
```

`load_panel_html()` 在启动时把 `CSS_MODULES`、`JS_MODULES` 顺序拼接，替换
`/*__TOKENS__*/`、`/*__CSS__*/`、`//__JS__`，产出一个**自包含的单文件 HTML** 交给 pywebview。

理由：pywebview 加载本地资源需要额外的目录路由与打包配置，而面板只有 ~30KB 文本；
拼一个字符串换掉整套静态资源服务，收益远大于成本。拆分只服务开发可维护性，不是运行时形态。

代价与约束：**JS 模块顺序即依赖顺序**，`M` 命名空间先由 `state.js` 建好；契约测试
`test_panel_composes_all_modules` 会对合成结果抽查各模块的标志函数，防止漏拼。

## 2. 聊天流：单向轮询 + 乐观回显

面板是"哑终端"，所有状态都在 Python 侧：

| 方向 | 机制 | 频率 | 说明 |
| --- | --- | --- | --- |
| Python → JS | `pywebview.api.snapshot()` | 200ms | 单次拉取全量快照（状态/宠物矩形/消息/发送中） |
| JS → Python | `pywebview.api.send(text)` | 用户触发 | 只入队，立即返回 |
| 外部 → Python | `control.json` | 每 tick 读 | `mascot ctl send --text` 走这里，供脚本/验收 |

没有 WebSocket、没有事件推送：200ms 轮询在 340×460 的面板上不可感知，却省掉了双向通道的
生命周期管理（页面刷新、桥接重连、消息乱序）。这是"先能用再优化"的刻意选择，M5 之后若要
做 streaming token，再加一条单向 push 通道，不动现有拉取。

**为什么发送只入队**：`send()` 跑在 UI 线程（pywebview 的桥接回调），HTTP 请求一旦卡住
2s，整个面板就冻结。所以 `send_text()` 只做校验 + 入队，真正的 `provider.send()` 在
worker 线程的 `_drain_sends()` 里执行。

**乐观回显**：用户点发送后先在本地插入一条 `pending` 气泡，等下一轮快照里出现同文本的
user 消息再撤掉。这样"网络慢"不会让用户以为没点上。相同文本判重，避免双气泡。

**消息合并与分桶**：相邻同角色消息合并为一个气泡（减少视觉噪音），时间按 今天/昨天/日期
分桶。渲染全程 `createElement` + `textContent`，`innerHTML` 一次都不用——消息来自外部
provider，必须按不可信数据处理。

## 3. 降级矩阵（后端不可用的四种表现）

| 场景 | 状态机 | 面板表现 | 数据 |
| --- | --- | --- | --- |
| 探测失败 | tracking → degraded | 红点 + 琥珀横幅 + "后端不可达，消息暂时无法收发（离线可用）" | 历史消息保留 |
| 发送失败 | 保持当前态 + `PROVIDER_DOWN` 事件 | 用户消息保留，`sending` 复位，横幅出现 | 错误文案进 `error` |
| 历史失败 | 不降级 | 消息区空，`provider_detail` 记原因 | 不阻塞面板显示 |
| `--provider null` | 不降级（刻意离线） | 正常面板，Null 后端回显 | 本地内存 |

关键取舍：**历史拉取失败不降级**。历史是"锦上添花"，为它把整个面板标红会让用户误以为
桌宠坏了；只有"发不出去"才是真降级。

## 4. 这轮踩到的坑（都是真机复现的）

1. **`background_color="#01000000"` 直接抛 `ValueError`**：pywebview 只接受 6 位 hex，
   透明窗口不需要设它，去掉即可。
2. **忘记 `js_api=` 时面板"活着但不画"**：`window.pywebview.api` 是 undefined，JS 轮询
   第一句就抛异常，页面停在初始态。所有桥接故障都是"静默"的，验收必须看截图而不是看进程存活。
3. **`state.json` 先截图后落盘**：原先 `_apply()` 先写快照再执行副作用，导致文件里短暂出现
   "state=degraded 但 degraded=false"的自相矛盾。改为**副作用先落地、再落盘**。
4. **WSL→Windows 互操作会过滤环境变量**：`MASCOT_PROVIDER_BASE_URL` 传不进 Windows 进程
   （WSLENV 机制只放行白名单），于是加了 `--provider-url` 参数。凡是验收用的覆盖项都走参数，
   不赌环境变量。
5. **Windows 控制台 stdout 是 GBK**：通过管道读回来中文变 `�`。CLI 启动时把
   stdout/stderr 强制 `reconfigure(encoding="utf-8")`，脚本同理。
6. **上次异常退出留下的 `control.json` 会被下一次启动消费**：等于"幽灵消息"。worker
   启动时先删掉控制文件。

## 5. 验收结果（真机 Windows 10 / 2560×1600 @150%）

`scripts/verify_m4.py`（独立进程驱动，9 项全过）：

```
[ok] panel_follows_pet: TX Mascot.exe 1616,272 180x180
[ok] history_loaded: 9
[ok] ctl_send_accepted
[ok] user_message_stored / assistant_reply_received
[ok] not_sending_after_reply / provider_not_degraded
[ok] ctl_stop / process_exited
RESULT: PASS
```

截图：`evidence/m4-chat.png`（历史 3 条 + 两轮问答，时间分桶、左右气泡、输入框单行）、
`evidence/m4-panel.png`（首轮联调）、`evidence/m2-degraded.png`（降级态）。

Linux：ruff 0 / pyright 0 / pytest 58 passed（含 4 个 provider 契约 + 6 个 runtime 单测）。

## 6. 已知缺口（交给 M5 / P1）

- 没有流式输出：一次 `send` 只有一个最终答复（streaming 需要新增 push 通道）。
- 消息只存在内存 + `state.json`，重启后靠 `provider.history()` 重新拉；本地持久化未做。
- 长消息折叠阈值固定 12 行，未按面板高度自适应。
- 面板没有键盘焦点管理（`Esc` 收球、`↑` 编辑上一条还没做）。
