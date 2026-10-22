# M28 待机球的单击不再硬等 350ms：双击时间窗可配置

## 动机

M25 给待机球加了「单击开面板 / 双击回右下角」，代价是单击要等 350ms 双击窗口过去才生效
（已知缺口：「待机球单击开面板有 350ms 双击窗口延迟」）。350ms 是"合理但偏慢"的默认值：
嫌慢的用户会真切感到延迟，而不用双击的人根本不需要这个手势。

M28 把窗口做成配置 `click_window_ms`：

- `350`（默认）：保持 M25 的手势，单击等窗口、双击复位；
- `0`：关掉双击手势，单击**立即**开面板（实测 23–26ms，即一个事件循环的延迟）。

配置项走的是 M12/M19 已有的 config 写回 + 热重载通道，所以改完不用重启。

## 改法

- `src/mascot_core/config.py`：`Settings` 新增
  `click_window_ms: int = Field(default=350, ge=0, le=2000)`，并加入 `HOT_FIELDS`
  （改它属于热字段，不提示 restart_required）。
- `src/mascot_core/click.py`：
  - 构造函数拦负数：`if window_ms < 0: raise ValueError("window_ms 不能为负")`；
  - `click()` 开头：`if self.window_ms <= 0: self._first_ms = None; return SINGLE`
    —— 0 表示「没有双击概念」，每次点击都是单击。`tick()` 自然永远返回 None。
- `src/mascot_app/runtime.py`：
  - `self._click_gate = ClickGate(self.settings.click_window_ms)`；
  - `_on_ball_click()` 从「拿 `_ball_press_ms` 自己算」改成调 `ClickGate.click(now_ms)`：
    `DOUBLE → _reset_ball_to_corner()`、`SINGLE → post(Event.CLICK_BALL)`；
  - `_maybe_reload_config()` 在热重载成功后同步 gate：
    `if self._click_gate.window_ms != float(self.settings.click_window_ms): self._click_gate = ClickGate(...)`；
  - `snapshot()["settings"]` 增加 `click_window_ms`，验收脚本与 `ctl status` 都能看到。
- 单测 `tests/unit/test_click.py`：`test_negative_window_rejected`（-1 抛 ValueError）+
  `test_zero_window_disables_double_click`（0 时两次连点都返回 SINGLE、`pending` 为 False、`tick` 为 None）。

## 验收（`scripts/verify_m28.py`）

无宠物启动（null provider），真实鼠标点击待机球：

1. `config set click_window_ms 0` → 启动 → `snapshot.settings.click_window_ms == 0`；
2. `measure_open()`（3 次「ctl to-ball → 等 idle → 点球 → 等 idle_open」取**最快**）→ 断言 < 0.35s；
3. 不重启，`config set click_window_ms 350` → `hot=true`、热重载后 snapshot 同步为 350；
4. 再 `measure_open()` → 断言 ≥ 0.25s（要等时间窗）。

Windows 实测（两轮）：

| 项 | 第 1 轮 | 第 2 轮 |
| --- | --- | --- |
| `open_delay_zero_ms` | **0.023 s** | **0.026 s** |
| `zero_window_fast` | true | true |
| `open_delay_default_ms` | **0.373 s** | **0.369 s** |
| `setting_reloaded` | true | true |
| `opens_after_window` | true | true |
| `exit_code` | 0 | 0 |

回归：`verify_m13/m24/m25/m26/m27` 全 exit 0、`ok: true`（M25 的双击复位仍按默认 350ms 工作）；
Linux `pytest 180 passed / 1 skipped`、ruff 0、pyright 0。

## 坑

1. **冷启动首击会假失败**：第一版验调用单次计时，0ms 那轮测出 **0.635s**（`zero_window_fast=false`），
   重跑又变成 0.026s——Windows 上进程刚起来时第一次鼠标注入 + 窗口消息的延迟不稳定。
   改成 3 次取最小值后两轮都稳定在 23–26ms。**结论：任何"点击到状态变化"的计时验收都要重复取样取最快。**
2. **0 值语义要显式写在三处**：`Field(ge=0)`（允许 0）、`ClickGate` 提前返回（0 不挂起）、
   文档/注释（0 = 关掉手势）。只改一处会出现「配置接受 0 但行为仍等 350ms」的静默错误。
3. **热重载要重建 gate 而不是改字段**：`ClickGate` 可能正挂着一个待确认的单击，
   直接改 `window_ms` 会让那个挂起的点击按新窗口结算；重建对象等于丢弃挂起状态，语义更干净。
4. **snapshot 不加字段验收就没法断言**：`ctl status` 的 `settings` 是验收与排障的唯一入口，
   每加一个热配置项都要同步加进去。

## 遗留

- 默认值仍是 350ms：不用双击的用户需要自己 `config set click_window_ms 0`。
  是否把默认改成 0、双击改成别的入口（如右键菜单已有「小球回到右下角」），留给后续里程碑决定。
- 0 窗口下就只剩单击手势；没有"长按"之类替代手势。
- 时间窗上限 2000ms 是拍的，没有实测依据。
