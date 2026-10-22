# M18 已安装版本目录：列举、回收、真回滚

## 动机

安装布局是"一个版本一个不可变目录 + current.txt 指针"（docs/19-m5-delivery.md），
每次升级都新增约 45MB 的目录（exe 8MB + _internal 依赖），旧目录**从来没人删**——升级十次就是 450MB。
同时 `rollback.bat` 生成时只认得"停掉新版 → 启动 E:\TX-Pet 冻结旧版"，
而 tx-pet 之后真正装过的上一版明明是 `app/<version>` 里的东西，回滚路径却指向了别的项目。

M18 补三件事：

1. `mascot versions`：列出 app/ 下所有版本目录、大小、哪个是 current；
2. `mascot versions --prune --keep N`：回收旧目录，**current 永不删**；
3. `install-win.sh` 装完自动按 keep=2 回收，并把 `rollback.bat` 指向严格更旧的上一版本
   （没有再退回 E:\TX-Pet）。

## 实现

### `src/mascot_core/versions.py`（纯逻辑，零平台依赖）

| 函数 | 作用 |
| --- | --- |
| `is_version_name(name)` | 目录名是否像版本号（`0.1.0` / `1.2` / `2.0.0-beta.1`） |
| `version_key(name)` | 转成可排序整数元组（预发布段按 0），保证 `0.10.0 > 0.9.0` |
| `read_current(app_dir)` | 读 `current.txt`（在 app 的上一级），非法内容返回 None |
| `list_versions(app_dir)` | 只要版本目录，标 current，算每个目录的真实字节数，按新到旧 |
| `pick_prune(rows, keep, current)` | 保留清单：current 必留，其余按新到旧留满 keep 个 |
| `prune_versions(app_dir, keep, dry_run)` | 真删（`shutil.rmtree`），返回 kept/removed/freed_bytes |

双保险：删除前核对 `target.parent == app_dir` 且名字像版本号，`backup/` 这类目录不会被误删。

### CLI

```
mascot versions                       # 列举（JSON）
mascot versions --prune               # 回收，默认 keep=2
mascot versions --prune --dry-run     # 只报告
mascot versions --app-dir <path>      # 验收时指定目录，不碰真实安装
```

### `scripts/install-win.sh`

装完 current.txt 后调刚装好的 exe 自带的 `versions --prune --keep "$KEEP"`
（`KEEP` 环境变量，默认 2）——"谁能列目录"只有一个实现，不在 shell 里重写一遍排序。

然后用 `sort -V` + `awk` 找**严格小于 current** 的最新版本作为 `PREV`，
写进 rollback.bat：有 PREV 就启动它并把它设成自启，没有才退回 E:\TX-Pet。
（用"严格更旧"而不是"除 current 外最新"，是为了降级安装时不会把"回滚"变成"回滚到更新版"。）

## 验收（`scripts/verify_m18.py`，Windows 15/15 PASS）

| 项 | 断言 |
| --- | --- |
| list_exit_0 | `versions` 退出 0、`ok:true` |
| list_versions | 0.3.0/0.2.0/0.1.0 从新到旧 |
| current_marked | 只有 current.txt 里那个标 current |
| sizes_listed | 每个目录的 `size_bytes` 等于实际文件大小 |
| backup_not_listed | 非版本目录不参与列举 |
| dry_run_reports | `--dry-run` 报出要删 0.1.0、`dry_run:true` |
| dry_run_keeps_dirs | dry-run 后目录仍在 |
| dry_run_freed | 预估释放字节数正确 |
| real_prune_exit_0 | 真删退出 0、`dry_run:false` |
| real_prune_removed | 只删 0.1.0 |
| real_prune_dirs | 删后只剩 0.2.0/0.3.0/backup |
| backup_survived | backup/ 里的文件没被动 |
| current_never_deleted | current 是最旧版本时，keep=1 只删更新的那个 |
| real_install_current | 真实安装目录里列举的 current 与 current.txt 一致 |
| real_install_total | 真实安装目录总字节数 > 0 |

安装脚本的端到端也手工验过：造 `0.0.7/0.0.8/0.0.9` 三个假版本目录，
`KEEP=2 install-win.sh` 后只剩 `0.0.9` 与 `0.1.0`，`回滚目标 = 0.0.9`；
清掉假目录再装一次，回滚目标回到 `（无，回滚到 E:\TX-Pet）`。

## 坑

1. **prune 在 dist 里必须是新 exe**：install-win.sh 用的是刚装好的 exe 的 `versions` 命令，
   如果 dist 还是旧构建（没有该子命令），prune 静默失败（`|| true`），旧目录不动。
   验证 prune 前必须先 `build-win.sh`。
2. **keep 是"总数"不是"额外保留数"**：`keep=2` 保留 current + 1 个旧版；
   只有两个目录时看不出删除，造三个才能验证。
3. **版本排序不能按字典序**：`0.10.0` 会排在 `0.9.0` 前面；python 侧用 `version_key`，
   shell 侧用 `sort -V`。
4. **cmd 批处理的 `if (...) else if (...)`**：两段都写 `if exist ... (` 是合法写法，
   但必须 CRLF（脚本里已有 `sed -i 's/$/\r/'` 收尾）。

## 遗留

- 回收策略固定保留 2 个版本，未做"按总磁盘占用回收"；
- 没有 `mascot rollback` 子命令（回滚仍靠 rollback.bat）；
- 版本目录大小按文件遍历统计，版本多时略慢（当前 2 个，可忽略）。
