# M12 配置写回与运行态开关持久化

日期：2026-10-22 深夜
前置：M9（DND）、M11（流式）

## 1. 问题

两件事在 M11 结束时都还是"半截"：

1. **配置只能读不能写**。`load_settings()` 早就支持 TOML（`load_settings` 里用
   `TomlConfigSettingsSource`），但**没有任何写入口**。用户想把 `fps` 从 10 调到 20、
   把 `provider_base_url` 指向自己的后端，只能自己去找
   `%LOCALAPPDATA%\mascot\config.toml` 手写 TOML——而文件默认根本不存在，
   连"该写什么键"都得翻源码。
2. **DND / 暂停不跨重启**。M9 把免打扰做成运行时字段 `_dnd`，进程一退就丢。
   用户晚上开了免打扰，第二天开机又变成会弹面板的默认态。docs/25 的遗留里写着这一条。

## 2. 配置写回

新增 `src/mascot_core/configfile.py`（**不用 tomlkit**，读用内置 `tomllib`，
写用 40 行极简序列化）：

| 函数 | 作用 |
| --- | --- |
| `known_keys()` | `Settings.model_fields` 的键，顺序稳定 |
| `coerce_value(key, raw)` | 命令行字符串 → 字段类型（bool / int / float / str / Path / tuple） |
| `read_config_file(path)` | 读现有 TOML，不存在返回 `{}`，坏了抛 `ValueError` |
| `write_config_file(values, path)` | 原子写（`.tmp` + `replace`），只写已知键 |
| `set_config_value(key, raw, path)` | 转换 + `Settings(**payload)` 校验 + 落盘 |
| `unset_config_value(key, path)` | 删键，返回是否真的删了 |

**关键设计：先用 Settings 校验再落盘**。`Settings(**payload)` 会把类型错误和
`Field(ge=1, le=60)` 这类范围约束一起兜住——所以 `mascot config set fps 999`
直接 rc=2 返回 `BAD_VALUE`，文件一个字节都不会动（`verify_m12.py` 的第 5 项就测这个）。

CLI：

```bash
mascot config path                    # {"path": "...config.toml", "exists": false}
mascot config show                    # file + effective（含环境变量覆盖后的结果）
mascot config get fps                 # 当前生效值
mascot config set fps 20              # 落盘 + restart_required: true
mascot config unset fps               # 回到默认
```

`show` 同时给 `file` 与 `effective` 两份：前者是磁盘上写了什么，后者是三级覆盖
（默认值 < TOML < `MASCOT_*` 环境变量）之后真正生效的值。两者不一致时就说明环境变量在
覆盖文件——这是排查"我明明改了配置却不生效"的唯一可靠手段。

## 3. 运行态开关持久化

新增 `%LOCALAPPDATA%\mascot\runtime.json`（`{"dnd": bool, "paused": bool}`），
由 `runtime.load_flags()` / `runtime.save_flags()` 原子读写：

- `Runtime.__init__` 里 `flags = load_flags()`，`_dnd` / `_paused` 的初值来自它。
- 托盘菜单的 `toggle_pause` / `toggle_dnd` 与 `ctl pause|resume|dnd on|off` 走的是
  同一条 `_drain_commands` 路径，所以**两处都调 `save_flags()`**，不存在"托盘记住了、
  ctl 没记住"这种分裂。
- 读失败（文件损坏/权限）→ 返回 `{}`，等于默认态；写失败 → 只 `log.warning`。
  **桌宠本体不能因为记不住一个开关而启动失败。**

为什么放在 `runtime.json` 而不是 `config.toml`：`config.toml` 是**用户意图**
（我想跑成什么样），`runtime.json` 是**上次运行留下的状态**（上次我把面板收起来了）。
两者混在一起会出现"用户手工编辑配置 → 被进程退出时的状态覆盖"的经典事故。

## 4. 验收

`scripts/verify_m12.py`（16 项，真实 Windows 机器，全过）：

| 组 | 检查 |
| --- | --- |
| 配置写回 | config_set_ok / config_file_written（含 `fps = 20` 字面）/ config_get_roundtrip / show_effective_fps |
| 拒绝非法 | unknown_key_rejected（rc 2）/ out_of_range_rejected（fps=999，rc 2） |
| 第一次运行 | run1_tracking / run1_flags_default_off / run1_both_on（dnd+paused）/ flags_file_written / run1_exit 0 |
| 重启恢复 | run2_restored_dnd / run2_restored_paused / run2_flags_cleared / run2_exit 0 |
| 收尾 | cleanup_config（unset 后 removed=true） |

日志里能直接看到 `dnd: on` → 退出 → 新进程 `dnd: off`（第二次运行里我们主动关掉），
且 second run 的 snapshot 一启动就是 `paused: true, dnd: true`。

## 5. 回归

- Linux：ruff 0 / pyright 0 / pytest 全绿（新增 `tests/unit/test_configfile.py` 12 项：
  roundtrip、保留其它键、未知键、非法布尔、范围校验、unset、环境变量优先级、
  flags roundtrip、损坏文件降级、Runtime 启动即带上持久化开关）。
- Windows：M12 16/16；`verify_m9.py`（DND）/ `verify_m11.py`（流式）重跑通过。

## 6. 遗留

1. `config set` 只支持扁平键，不支持嵌套表（`[panel]` 之类）；当前 Settings 全是扁平的，够用。
2. 写回会丢注释（我们生成的文件只有一行头注释）。手工编辑过的文件被 `set` 一次后会变整齐——
   对只有 19 个键的配置可接受，将来若要保注释再引 tomlkit。
3. `runtime.json` 目前只记 dnd/paused；窗口位置、上次面板/小球态还没记（M13 候选）。
4. `config set` 后需要重启实例才生效（`restart_required: true`），没有做热重载。
