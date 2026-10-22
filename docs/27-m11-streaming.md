# M11 流式增量渲染与停止生成

日期：2026-10-22 夜
前置：M10（legacy provider + auto 选路）

## 1. 为什么要做

M10 结束时聊天是「整段到达」：用户按下发送后，界面上除了发送按钮变灰之外没有任何
反馈，直到后端把整段回复写完才一次性出现。真实旧后端（DeepSeek 对话）一次回复可能
要 10–60 秒，这段时间面板看起来像卡死。

M11 的目标只有两条：

1. 回复逐片出现在气泡里（打字机效果），并且明确显示「还在写」。
2. 写的过程中可以停：停下后已收到的部分保留为一条普通消息，不丢。

## 2. 契约：send_stream 是可选鸭子类型

```python
# src/mascot_core/contract.py
class SendCancelled(Exception):
    """流式发送被用户取消。调用方应保留已收到的部分内容。"""

class ChatProvider(Protocol):
    def send(self, text: str) -> Message: ...
    # 可选：若 provider 实现 send_stream，运行时优先使用它。
    # 未实现的 provider 会退化为 send() + 一次性 on_delta。
```

为什么不做成协议必选方法：协议是给「所有后端」的约束，而 NullProvider / WslProvider
这类后端天然拿不到增量。把它们都改成 fake 流式只会增加噪音。运行时用
`getattr(provider, "send_stream", None)` 判断，缺失就整段交付——这一条同时保证了
M10 的行为对老后端零回归。

## 3. 数据流

```
SSE 行 → LegacyProvider.send_stream
      → on_delta(piece)            （worker 线程）
      → Runtime._on_delta: 持锁 append 到 _stream_text，cancel 已置位则 raise SendCancelled
      → snapshot()["streaming"] = {"active": True, "text": <累计>}
      → 面板 JS 每 200ms 轮询 → chat.js 追加 .msg.streaming 气泡 + .caret
```

关键点：

- **取消不靠打断线程**。worker 线程正在阻塞读 SSE，不可能被安全 kill。做法是置
  `_cancel` 事件，下一次 `_on_delta` 回调时抛 `SendCancelled`，异常沿栈回到
  `_send_streaming`，在那里把 `_stream_text` 落成部分消息。代价是「最多晚一片才停」，
  实测延迟 `chunk_delay`（0.35s）量级，可接受。
- **部分回复的 msg_id 前缀是 `partial-`**，方便测试与将来做「这条被中断」的标记。
- **streaming 只在内存里**，不写进 state.json 之外的地方；面板刷新后靠 history 重建。

## 4. 各 provider 的流式形态

| provider | send_stream 行为 | 说明 |
| --- | --- | --- |
| legacy | 逐行读 `data:` SSE，逐片回调；`[SESSION:]` 记录会话并结束，`[ERROR]` 抛错，`[DONE]` 结束 | 真正的增量来源 |
| wsl | 直接 `send()` 再 `on_delta(全文)` | 新契约是整段 JSON，没有流式通道 |
| null | `return self.send(text)` | 离线回显，无 UI 价值但保证协议一致 |
| auto | 转发给 `_active.send_stream`（不存在则 `_active.send`） | 少了这层转发就会出现「auto 模式永远整段到达」 |

## 5. SSE 分片空格 bug（值得单独记）

旧实现读 SSE 用 `line.strip()`，然后 `piece = stripped[5:].lstrip()`。SSE 的分片是按
token 切的行，`data: hello` 与 `data: world` 拼起来应该是 `hello world`，但
`lstrip()` 把词间空格吃掉了，结果渲染成 `helloworld`。

正确做法：只剥掉行长结尾的 `\r\n`，并且只剥掉**一个**协议前导空格：

```python
raw = raw_line.decode("utf-8", errors="replace")
line = raw.rstrip("\r\n")
if not line.startswith("data:"):
    continue
piece = line[5:]
if piece.startswith(" "):
    piece = piece[1:]
```

`tests/contract/test_legacy_provider.py::test_stream_pieces_keep_their_spaces` 用
`data: hello` + `data:  world`（第二个分片自带前导空格）锁住这个行为：
期望 `"hello  world"`（两个空格都保留）。

## 6. 停止生成的三个入口

1. 面板按钮：sending 时「发送」变「停止」（`button.primary.stopping`，amber），
   点击调 `M.api.stop()` → `JsApi.stop()` → `Runtime.cancel_send()`。
2. CLI：`mascot ctl cancel-send`（写 control.json `{"cmd":"cancel_send"}`）。
3. 运行时自身的 `_poll_control` 分支——**这一条之前漏了**，导致 `ctl cancel-send`
   写了文件却无人消费，只有面板按钮能用。补上后两条路径等价。

`cancel_send()` 在空闲时返回 False（no-op），不会误吞下一条消息。

## 7. 前端渲染细节

- 签名里带上 `'#' + live.length`：否则流式期间 messages 数组没变，`renderMessages`
  会认为「渲染结果一致」而跳过重绘，气泡永远是空的（这个坑在 M4 就吃过一次，
  当时是 `lastSignature = ''` 撞上空渲染）。
- 空文本先显示 `.thinking`「思考中」（三个点跳动动画），有第一片后换成文本 + `.caret`。
- `prefers-reduced-motion: reduce` 时关掉 caret / dots 动画。

## 8. 验收

`scripts/verify_m11.py`（15 项，真实 Windows 机器）：

| 检查 | 结果 |
| --- | --- |
| panel_follows_pet | PASS |
| ctl_send_accepted | PASS |
| stream_partials_observed（state.json 里观察到中间态） | PASS（78–98 次采样） |
| partial_grows_monotonically | PASS |
| reply_completed | PASS |
| partial_is_prefix_of_reply | PASS |
| streaming_reset | PASS |
| second_send_accepted | PASS |
| stream_active_before_cancel | PASS |
| cancel_accepted | PASS |
| partial_message_kept | PASS |
| partial_short_of_full_reply | PASS |
| not_degraded | PASS |
| ctl_stop / process_exited | PASS |

取消时保留 17–18 / 84 字，符合「最多晚一片」的预期。

截图：

- `evidence/m11-streaming.png`：流式气泡带 caret，发送键显示 amber「停止」。
- `evidence/m11-stopped.png`：取消后气泡保留已收到的部分文本，按钮恢复「发送」。

## 9. 回归

- Linux：ruff 0 / pyright 0 / pytest **98 passed, 1 skipped**。
- Windows：`verify_m11.py` 15/15；`verify_m4.py` / `verify_m7.py` / `verify_m10.py`
  均重跑通过（流式改动落到 runtime 共享路径，回归面较大）。

## 10. 遗留

1. **增量不落盘**：streaming 文本只在内存，实例崩溃则部分回复丢失；将来可在
   `_on_delta` 里按 200ms 节流写 state.json。
2. **history 无真实时间戳**（M10 遗留）：旧后端 `/api/pet/news` 不带 ts，用 now 递减伪造。
3. **取消语义是「停读」不是「停写」**：后端仍在生成（旧后端没有 cancel 接口），
   只是我们不再读、不再计入。将来若后端提供取消端点可补。
4. **auto 选路每次 health 失败都会重探**：流式期间不再探（worker 单线程串行），
   所以不会在生成中途切换后端。
