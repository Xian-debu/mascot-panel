# M19 配置热重载：改 config.toml 不用重启

## 动机

M17 把写回改成了保注释，但「改完必须重启」还在（progress 已知缺口）。
桌宠是常驻进程，改个 fps 要退出再开，体验上说不过去。

M19 把配置分成**热字段**与**冷字段**两类：

- 热字段：每一 tick / 每次 poll 都从 `self.settings` 现读，换了立刻生效；
- 冷字段：牵涉窗口重建、后端重新握手（`panel_size`、`provider`、`pet_window_class` …），
  改了不崩、不假装生效，只把字段名写进 `state.json` 的 `config.restart_required`。

## 实现

### `src/mascot_core/config.py`

```python
HOT_FIELDS = ("fps", "poll_interval_ms", "orbit_speed", "orbit_period_s",
              "ball_ratio", "orbit_gap", "follow_offset", "lost_frames", "notify_pulse")

def merge_hot(old, new) -> tuple[Settings, list[str]]:
    merged = old.model_copy(update={n: getattr(new, n) for n in HOT_FIELDS})
    restart = sorted(n for n in type(old).model_fields
                     if n not in HOT_FIELDS and getattr(old, n) != getattr(new, n))
    return merged, restart
```

纯函数、不碰文件，单测直接比字段。

### `src/mascot_app/runtime.py`

- `Runtime(..., config_path=..., pinned=...)`：记住配置文件路径；`pinned` 是
  「命令行/环境变量已显式覆盖的字段」，这些字段文件里的值本来就不生效，不该报重启。
- 主循环每秒 `_maybe_reload_config()`：比较 `(st_mtime_ns, st_size)`，
  变了就 `load_settings(config_path)` → `merge_hot` → 替换 `self.settings`；
  解析失败只 `log.warning` 并保持旧配置，绝不让运行中的实例崩。
- `interval` / `frame_s` 从循环外的一次性计算挪进循环内（否则 fps 热重载没意义）。
- `snapshot()` 新增：

```json
"settings": {"fps": 30, "poll_interval_ms": 200, "orbit_speed": 1.0},
"config":  {"path": "...", "reloads": 2, "restart_required": ["log_level"]}
```

### `config set / unset` 的返回值

增加了 `hot` 与真实语义的 `restart_required`（以前恒为 `true`）：
改 fps 返回 `{"hot": true, "restart_required": false}`，改 log_level 返回 `true`。

## 验收（`scripts/verify_m19.py`，Windows 17/17 PASS）

| 项 | 断言 |
| --- | --- |
| boot_fps_10 / boot_no_reload | 启动读临时配置 fps=10，reloads=0 |
| config_path_tracked | state.json 里 config.path 指向传入的 --config |
| idle_no_reload | 配置没动时等 2s，reloads 仍是 0（不会平白重载） |
| set_exit_0 / set_marks_hot | `config set fps 30` 成功，返回 hot=true、restart_required=false |
| fps_hot_applied / reload_counted | ≤8s 内 state.settings.fps==30、config.reloads≥1 |
| hot_not_restart | 热字段不产生 restart_required |
| cold_set_exit_0 / cold_set_marks_restart | `config set log_level DEBUG` 返回 hot=false、restart_required=true |
| cold_reports_restart | ≤8s 内 state.config.restart_required 含 log_level |
| instance_alive | 冷字段改了实例不重启 |
| bad_value_rejected | fps=999 被 CLI 拒绝（退出码 2） |
| alive_after_bad_value | 被拒后实例仍活着 |
| stop_ok / exit_code | ctl stop 正常，进程退出码 0 |

回归：verify_m13 ~ m18 全部 exit 0；Linux pytest 149 passed / ruff 0 / pyright 0。

## 坑

1. **环境变量会盖住 TOML**：验收里用 `pet_window_class` 当冷字段永远测不出来，
   因为 `MASCOT_PET_WINDOW_CLASS` 已把值钉死。`_pinned` 自动把
   `os.environ` 里存在的 `MASCOT_<FIELD>` 排除出 restart_required，验收改用 `log_level`。
2. **`--provider null` 也是覆盖**：不 pin 的话每次热重载都会报 `provider` 需要重启（假警报）。
3. **mtime+size 不够严谨但够用**：同一纳秒内改两次同长度内容会漏一次；
   真实编辑器保存必变 mtime，验证也覆盖了。
4. **不要把 `interval`/`frame_s` 留在循环外**：那是热重载"看起来生效"的假象来源。

## 遗留

- 冷字段不会自动重建窗口/后端（提示重启，不做热重建）；
- 只监视单一配置文件路径，不支持配置 include；
- `reloads` 不落盘（重启归零）。
