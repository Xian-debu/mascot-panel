# M21 health 探测独立短超时：降级横幅从 4.3s 提前到 1.9s

## 动机

M8 的遗留：后端不在时降级横幅要 2.1s+ 才出现。实测比文档更糟——
本机 `legacy: timed out` 时 **4.29s** 才出降级（`boot.state_degraded = 4235ms`）：
`AutoProvider.health()` 串行探两次（legacy 2s 超时 + wsl 2s 超时），
而这两个探测用的是**业务超时** `provider_timeout_s = 2.0`。

health 只是「本机回环端口活不活」，跟一次聊天请求的超时要求完全不同。
M21 给它单独一个 `health_timeout_s`（默认 0.8s，可配，冷字段）。

## 改动

### `src/mascot_core/config.py`

```python
provider_timeout_s: float = Field(default=2.0, gt=0.1)
# health 是启动路径上的串行探测（auto 连探两次），比业务超时更短才不至于拖慢降级
health_timeout_s: float = Field(default=0.8, gt=0.05, le=10.0)
```

### providers

- `LegacyProvider(..., health_timeout_s=None)`、`WslProvider(..., health_timeout_s=None)`：
  不给就回落到 `timeout_s`（保持旧行为，单测里可显式传）；
- `_get(path, timeout=None)` 支持每次调用覆盖超时；
- `health()` 用 `self.health_timeout_s`，`history()`/`send()` 仍用业务超时；
- `AutoProvider(..., health_timeout_s=None)` 透传给两个子 provider；
- `make_provider()` 传 `health_timeout_s=settings.health_timeout_s`。

`snapshot()["settings"]` 增加 `health_timeout_s`，`ctl status` 能看到当前值。

## 验收（`scripts/verify_m21.py`，Windows 15 项全 PASS）

| 项 | 断言 |
| --- | --- |
| degrade_fast / degrade_elapsed_s | 无后端时 1.91s 出降级（旧 4.29s），阈值 < 3.0s |
| degraded_state / boot_mark_fast | state=degraded；`boot.state_degraded` < 3000ms |
| health_timeout_exposed | 快照 `settings.health_timeout_s == 0.8` |
| stop_after_down / exit_code_down | 降级态 ctl stop 正常、退出码 0 |
| healthy_fast / healthy_elapsed_s | 起假 legacy 后端（`/api/pet/status` → ok），0.27s 判定健康 |
| not_degraded | 健康后端时不降级 |
| stub_probed / wsl_not_probed | 假后端收到 `/api/pet/status`；legacy 成功就不再探 wsl |
| instance_alive / stop_ok / exit_code | 全程存活，stop 后退出码 0 |

回归：verify_m13 ~ m20 全部 exit 0；Linux pytest 155 passed / ruff 0 / pyright 0。

## 坑

1. **venv 的 `python.exe` 是转发器**：`Popen` 拿到的 pid 不是桌宠自己的 pid
   （pid 文件里是真解释器的 pid），`ctl stop` 按 pid 文件停进程、而验收等的是转发器，
   于是「进程明明停了、验收却超时」。验收里改用 `sys._base_executable` + `PYTHONPATH=venv/Lib/site-packages`
   直接起真解释器；ctl 子进程仍用 `sys.executable`（它只读写文件，不涉及 pid）。
2. **`ctl stop --provider-url` 会 argparse 失败**：`--provider-url` 是顶层参数，
   `ctl` 子命令没有它，退出码 2，表现成「stop 没反应」。stop 只需要 pid 文件，别传这些。
3. **健康探测不能沿用业务超时**：`auto` 串行探两次，业务超时会被乘二。

## 遗留

- `health_timeout_s` 是冷字段（provider 在启动时构建），改它要重启；
- http 层仍是 `urllib`，超时是 socket 级、不区分 connect/read；
- 后端「在线但引擎 missing」仍算 DEGRADED（不缩短，那是真实状态）。