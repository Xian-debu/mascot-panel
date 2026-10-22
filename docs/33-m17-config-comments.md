# M17 配置写回保留注释与未知键

M12 起 `mascot config set` 会把配置整份重建：每次写回都把文件洗成
`# mascot 配置（由 mascot config set 维护…）` + 已知键列表。
手写的注释、为了记笔记加的未知键、甚至 `[table]` 段全都会消失——
这对"可以手工编辑"的配置文件是硬伤。M17 把写回改成**按行编辑**。

## 改法

`src/mascot_core/configfile.py` 的写路径从"拼一份新文件"换成 `_render(values, existing)`：

- 逐行扫描原文件，只处理 `key = value` 形态的扁平键；
- 键在 `Settings` 里且在新值集合中 → 只替换这一行的值，**保留行内注释**（含原来的空格数）；
- 键在 `Settings` 里但不在新值集合中 → 删掉这一行（`unset` 的语义），它的行尾注释一起走；
- 键不在 `Settings` 里（用户自己的笔记键）→ 原样保留；
- `[table]` 段及其内容 → 原样保留；首行之后新补的键**必须插在第一个 `[table]` 之前**，
  否则会被 TOML 当成表内的键；
- 重复键只在"文件已经坏了"时出现（`tomllib` 本来就拒绝重复键），写回时折叠成第一条；
- 文件不存在 → 还是老的模板（表头 + `known_keys()` 顺序）。

几个细节：

- `_comment_index()` 逐字符扫，尊重引号与转义，所以 `provider = "a#b"` 里的 `#` 不算注释。
- `_bare_key()` 只认合法的扁平键（表头、注释、没有 `=` 的行都返回 `None`）。
- 写回仍是原子写：`config.toml.tmp` → `replace()`。

## 验收（scripts/verify_m17.py，12/12 PASS）

全程在临时文件上（`--config` 显式路径），不碰真实配置：

| 检查 | 结果 |
| --- | --- |
| `set_exit_0` | ✅ `config set fps 20` 返回 0 |
| `comment_kept` | ✅ 文件头注释与 `fps` 行尾注释都在 |
| `unknown_key_kept` | ✅ `custom_thing = "keep me"` 还在 |
| `table_kept` | ✅ `[extra]` 与 `note = "表里的也别动"` 还在 |
| `still_valid_toml` | ✅ `tomllib` 可读，`fps == 20` |
| `table_value_intact` | ✅ 表内值未被动 |
| `get_returns_20` | ✅ `config get fps` = 20 |
| `bad_value_rejected` | ✅ `fps=999` 被 Settings 拦下，退出码 2 |
| `file_untouched_on_reject` | ✅ 被拒时文件字节级不变 |
| `unset_exit_0` | ✅ `config unset fps` 返回 0 且 `removed=true` |
| `key_removed` | ✅ `fps =` 那行消失 |
| `comments_survived_unset` | ✅ 独立注释行与未知键都还在 |

Linux 侧新增 8 个单测（保留注释/未知键/表、新键插在表前、重复键折叠、幂等、
空文件建模板、unset 保留周边注释、字符串里的 `#`），`pytest` 135 passed；ruff 0 / pyright 0。

## 坑

1. **新键不能直接 append 到文件尾**：如果文件里有 `[extra]`，追加的键会被算进 `[extra]` 表，
   `Settings` 读不到它（表现为"set 成功了但值没生效"）。必须插在第一个表头之前。
2. **行尾注释跟着行走**：删键时它的 `# 注释` 一起删（留在文件里会变成孤立的注释，
   指向一个不存在的键）。独立注释行不受影响。
3. 重复键在 `set_config_value` 里根本读不进来（`tomllib` 先报 `Cannot overwrite a value`），
   所以这条只有 `write_config_file` 能修——单测覆盖的是后者的行为。

## 遗留

- 仍无热重载：`config set` 之后要重启进程（CLI 返回里已带 `restart_required: true`）。
- 只支持扁平键，不支持点号路径（`a.b`）与数组行内注释的复杂重排。
- 值被改写时不保留原值的写法（如 `1_000` 会变成 `1000`）。
