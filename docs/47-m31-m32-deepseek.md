# M31/M32：降级放行交互 + 直连 DeepSeek（A1/A2）

日期：2026-10-23 00:30 前后。路线：`/root/mascot-admin/docs/14-product-roadmap.md` 阶段 A。
M31 = A1（降级不再吞交互、降级也跟随），M32 = A2（DeepSeek 直连 provider，不再依赖本机 8890 Flask）。

## 为什么做
- 用户实测：安装了桌宠却「点球没反应、面板不跟随」，因为后端不可达 → 状态机进 DEGRADED →
  `state.py` 把 CLICK_CLOCK/CLICK_BALL 全判 IGNORED，`runtime.py` 主循环 `if not self._degraded: self._place_panel()`
  又跳过了定位。降级本应只影响「发消息」，不该冻结其它一切。
- 用户明确：不做旧版 UI 回退；key 直接用 `.bashrc` 的 DeepSeek（`DEEPSEEK_AUTH_TOKEN`），
  直连公网，不再要求先跑 `127.0.0.1:8890`。

## M31（A1）改动
- `src/mascot_core/state.py`：`Machine.push()` 在 DEGRADED 时对
  `{PET_FOUND, PET_LOST, CLICK_CLOCK, CLICK_BALL}` 做「内层转移」：
  以 `resume_state or IDLE` 为基态跑一次 `transition()`，成功则更新 `resume_state` 并把 effects 原样返回，
  状态仍是 DEGRADED（横幅/重试逻辑不变）。内层 IGNORED 时返回 `IGNORED:<EVENT>`，不产生副作用。
  这样降级下点时钟仍可收进环绕球、点球仍回面板、宠物出现/消失仍切换可见形态。
- `src/mascot_app/runtime.py`：主循环去掉 `if not self._degraded:` 守卫，降级也执行 `_place_panel()`（跟随/记忆位置恢复）。
- `src/mascot_app/runtime.py:_poll_provider`：健康探测只在状态真的翻转时推事件（`not self._degraded` 才推 DOWN，
  `self._degraded` 才推 READY），修掉每 5s 一条 `IGNORED:PROVIDER_DOWN/READY` 的日志刷屏；`provider_detail` 仍每次更新。
- 单测 `tests/unit/test_state.py` 新增 4 条：降级下 CLICK_CLOCK 从 TRACKING→（仍 DEGRADED，resume=ORBITAL，effects=收面板/显示球/启帧）、
  CLICK_BALL 从 ORBITAL→resume TRACKING、PET_FOUND 保留跟随、ORBITAL 下 IGNORED 保持原状。

## M32（A2）改动
- 新增 `src/mascot_app/providers/deepseek.py`（`DeepSeekProvider`）：
  - key 只从环境变量读：`DEEPSEEK_AUTH_TOKEN`，回退 `DEEPSEEK_API_KEY`；缺失时 `health()` 返回 DOWN + `NO_API_KEY`，
    发送抛明确错误（`缺少 DeepSeek key…`），**绝不落盘、不写日志**。
  - `health()`：`GET {base}/models`（Bearer），3s 超时；401/403 → `AUTH_REJECTED`，网络错误 → `PROVIDER_UNREACHABLE`。
  - `send_stream()`：`POST {base}/chat/completions`，`stream: true`，逐行解析 `data: {...}` 的 `choices[0].delta.content`，
    边收边 `on_delta()`（面板逐字增长），`[DONE]` 结束；空回复抛错。
  - 多轮上下文：`set_context(messages)` 由 runtime 在每次发送前注入最近 20 轮；发送成功把本轮 user/assistant 追加进内部 deque。
  - `history()` 返回空——本地 `history.json` 是消息真源，避免重复。
  - base_url 兼容 `.bashrc` 的 `DEEPSEEK_BASE_URL=https://api.deepseek.com/anthropic`：自动去掉 `/anthropic` 后缀。
- `src/mascot_core/config.py`：默认 `provider="deepseek"`、`provider_base_url="https://api.deepseek.com"`、
  新增 `provider_model="deepseek-chat"`、`provider_timeout_s=120`、`health_timeout_s=3.0`（公网抖动容忍）。
- `src/mascot_app/providers/__init__.py`：`make_provider` 支持 `deepseek`（传入 base/model/两个超时）；legacy/auto/wsl 保留。
- `src/mascot_app/cli.py`：`run --provider` 增加 `deepseek` 选项与 `--provider-model`；被 CLI 覆盖的字段进 `pinned`（配置热重载不覆盖）。
- `src/mascot_app/runtime.py:_send_streaming`：发送前 `setter = getattr(provider, "set_context")` 注入当前时间线。
- 单测 `tests/unit/test_deepseek.py` 5 条：无 key → DOWN/NO_API_KEY；history 空；set_context 过滤空文本；
  SSE 解析（假 urlopen 返回两段 delta + [DONE]，断言逐字回调与上下文追加）；`/anthropic` 归一化。
  另更新 `test_config.py`（默认 deepseek/base/model）与 `test_health_timeout.py`（3.0 / 120）。

## 真机验证（win-admin，2026-10-23 00:20–00:25）
- 启动：`Start-Process venv/Scripts/mascot.exe run --provider deepseek`，
  环境变量 `DEEPSEEK_AUTH_TOKEN`（来自 `/root/.bashrc`）+ `LOCALAPPDATA=C:\Users\Public\mascot-devstate`（隔离用户目录）。
- `state.json`：`state=tracking`、`provider=deepseek`、`degraded=false`、`provider_detail=""`，
  宠物 = 真实 `TX Mascot.exe`（ASUSMascot，HwndWrapper…）。
- `wshot` 面板截图：绿色状态点 + 「跟随中」，无降级横幅。
- 真实输入：win-admin `winput click/type/key enter` 在面板输入「你现在用的是哪个模型？」并回车；
  DeepSeek 回复「我正在使用DeepSeek最新版本的模型…」——两轮上下文都保留（它记得前一轮的「你好」）。
- 证据：`evidence/a2-deepseek-chat.png`（第一轮）、`evidence/a2-deepseek-typed.png`（真实键入的第二轮）。
- Linux 门禁：`uv run ruff check .` 0、`uv run pyright` 0、`uv run pytest` **192 passed / 1 skipped**。

## 踩过的坑
- WSL 里 `LOCALAPPDATA=... ./venv/Scripts/mascot.exe` 的环境变量**不会传给 Windows 进程**（cmd 实测仍是用户默认值）；
  必须用 `powershell.exe -Command "$env:...=...; Start-Process ..."`。
- WSL 当前目录是 UNC 路径时 cmd.exe 会警告并回退到 Windows 目录（不影响 PowerShell）。
- `pip install --force-reinstall` 中途失败会留下 `venv/Lib/site-packages/~ascot` 残留，导致之后 `import mascot_app` 失败；
  清掉 `~ascot*` 再重装。装完务必 `python -c "import mascot_app"` 复核。
- win-admin `winput` 必须显式 `--yes` 才是真注入；`click` 还要 `--expect-hwnd`（防盲点）。
- 健康探测每 5s 推一次同状态事件 → 日志刷屏（已按「只在翻转时推」修掉）。

## 遗留（下一步）
- 安装版拿不到 key：用户从开始菜单启动时没有 `DEEPSEEK_AUTH_TOKEN`。需要安装时写用户级环境变量（setx）或在设置页录入（B3）。
- 开发/安装共用 `%LOCALAPPDATA%\mascot`（A3/M33 状态目录隔离，用 `MASCOT_STATE_DIR`）。
- 用户 `%LOCALAPPDATA%\mascot\history.json` 里仍有我早期验收写入的假消息，需清理（只删验收条目）。
- 会话/消息操作（新建、切换、删除、编辑、版本、合并）仍缺（阶段 B）。