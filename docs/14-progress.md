# 进度报告（自动维护，供明早阅读）

> 每个里程碑完成后追加一节；每条含"做了什么 / 怎么验证 / 提交号 / 已知缺口"。
> 规划基线：`/root/mascot-admin/docs/10-plan.md`。

## M0 骨架与决策落地 — 完成（2026-10-22 夜）

**做了什么**
- 新仓库 `/root/mascot`：hatchling + src 布局，4 个包 `mascot_core / mascot_win / mascot_render / mascot_app`。
- 依赖锁定：`uv.lock`（33 包），`uv sync --group dev` 一次成功。
- `mascot_core`（零平台依赖，纯逻辑）：
  - `geometry.py`：矩形/屏幕夹取/跟随框/环绕球坐标/角度函数；
  - `hit.py`：命中测试（后登记者优先）；
  - `state.py`：IDLE/TRACKING/ORBITAL/DEGRADED 四状态纯函数状态机 + 降级记忆；
  - `config.py`：pydantic-settings，TOML 与 `MASCOT_*` 环境变量；
  - `contract.py`：`ChatProvider` 协议、`HealthState`；
  - `tokens.py`：HTML/CSS 与 PIL 共用设计 token。
- `mascot_app`：CLI `run/doctor/ctl`，JSON + exit code 契约；WSL/Null 两个 provider；JSON 行日志。
- CI：GitHub Actions，ubuntu + windows 双矩阵，ruff/pyright/pytest/doctor smoke。

**怎么验证（当时命令与输出）**
```
uv run ruff check .        -> All checks passed!
uv run pyright             -> 0 errors, 0 warnings
uv run pytest              -> 34 passed in 0.11s
uv run mascot doctor --offline -> {"ok":true,...} exit=0
uv run mascot doctor       -> provider wsl:down PROVIDER_UNREACHABLE（非 critical）exit=0
uv run mascot ctl status   -> {"ok":true,"data":{"running":false,...}} exit=0
```

**提交**：d3d11d7 init / 9872d14 core / 176c50c app / （CI 与本文档见下一提交）

**已知缺口**
- `mascot run` 仍是占位（exit 3 ENV_NOT_READY）：窗口接线在 M1/M2。
- 尚未在 Windows Python 上跑过：下一节 M0.5 处理。
