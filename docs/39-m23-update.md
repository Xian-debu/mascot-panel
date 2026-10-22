# M23 就地升级命令（mascot.exe update）

## 动机

进度里的已知缺口「无自动更新」：升级只能跑 scripts/install-win.sh（WSL + venv + dist），
普通用户手里只有一个安装好的 mascot.exe，拿到新版本（目录或 zip）没法自己装。

M23 提供 `mascot.exe update --from <目录|zip>`：就地装到 `app/<version>`，
原子切 `current.txt`，按 keep 回收旧目录——**和 install-win.sh 完全同一套目录模型**（M18 建立），
升级失败时 current.txt 不动，旧版本仍在。

不动的东西：不做网络拉取（没有更新服务器）、不校验签名（未签名是已知缺口）、
不自动重启（装完提示 `mascot.exe run`）。

## 改动

### `src/mascot_core/update.py`（纯逻辑，新增）

- `source_kind(source)`：目录必须含 `mascot.exe` → `"dir"`；`.zip` → `"zip"`；否则 ValueError。
- `_safe_extract(zip, dest)`：拒绝 `../` 与绝对路径（zip slip），逐成员流式写。
- `_locate_exe_root(extracted)`：zip 里多套一层目录（`mascot/mascot.exe`）也能找到。
- `install(source, app_dir, version, keep=2, dry_run=False, force=False)`：
  1. 校验版本号（`is_version_name`，`../evil` 之类直接拒）；
  2. 已存在同版本且无 `force` → 拒绝（不静默覆盖）；
  3. 先复制/解压到 `app/.incoming-<version>`，**成功后才**删旧目录、rename 成正式目录；
  4. 原子写 `current.txt`；
  5. `prune_versions(keep)` 回收旧目录，返回 `removed` / `freed_bytes`；
  6. 任何异常都清掉 `.incoming-*`，不留半成品。
- dry-run 只算计划：返回 `target`、`previous`、`would_remove`，一个字节都不写。

### `src/mascot_app/cli.py`

- 新增 `update` 子命令：`--from`（必填）、`--version`（默认推断）、`--keep`、`--dry-run`、`--force`、`--app-dir`；
- `_infer_version()`：源目录名/zip 名是版本号就用它，否则跑源里 `mascot.exe --version` 取末段；
- `_stop_running_instance()`：升级前用现有 ctl 通道 `stop` 正在跑的实例（Windows 会锁 exe/dll），最多等 8s；
- 错误分流：源/版本问题 → `code=UPDATE_SOURCE` / `UPDATE_REJECTED` 退出码 2；复制失败 → `UPDATE_FAILED` 退出码 5。

## 验收（`scripts/verify_m23.py`，Windows 26/26 PASS）

全部在临时 `--app-dir` 上跑，源目录里放一个假 `mascot.exe`（update 只负责复制与切指针）。

| 项 | 断言 |
| --- | --- |
| dir_install_exit_0 | `update --from <0.2.0>` 退出 0、ok=true |
| version_inferred_from_dir | 不传 `--version`，从目录名推断出 0.2.0 |
| installed_flag / previous_reported | installed=true、previous=0.1.0 |
| current_switched / exe_copied | current.txt 变 0.2.0，`app/0.2.0/mascot.exe` 存在 |
| old_version_kept | 0.1.0 目录仍在（回滚目标） |
| upgrade_exit_0 / pruned_oldest / freed_bytes | 装 0.3.0（keep=2）后回收 0.1.0，freed_bytes>0 |
| oldest_gone | 0.1.0 真的删了 |
| dry_run_exit_0 / dry_run_installed_false | `--dry-run` 退出 0、installed=false |
| dry_run_lists_removal | would_remove=[0.2.0] |
| dry_run_no_dir / dry_run_current_unchanged | 0.4.0 未创建，current.txt 仍 0.3.0 |
| existing_needs_force | 重装同版本 → 退出 2、code=UPDATE_REJECTED |
| force_overwrite_ok | `--force` 覆盖成功 |
| zip_install_ok / zip_exe_present / zip_internal_present | zip（多一层目录）装好，exe 与 `_internal/` 都在 |
| current_is_zip_version | current.txt=0.5.0 |
| bad_source_exit_2 / empty_dir_rejected | 不存在路径和空目录都退出 2、code=UPDATE_SOURCE |
| no_incoming_left / kept_two_versions / listing_intact | 无 `.incoming-*` 残留，目录只剩 0.3.0、0.5.0 |

回归：verify_m13 ~ m22 全部 exit 0；Linux pytest 168 passed / ruff 0 / pyright 0。

## 坑

1. **`subprocess.run(text=True)` 在 Windows 用 GBK 解码**：update 的报错信息是中文，
   验收脚本 `json.loads` 直接拿到空 stdout（UnicodeDecodeError 在读取线程里被吞），
   于是「退出码 2 但解析不出 code」。验收必须显式 `encoding="utf-8", errors="replace"`。
2. **不能先删再装**：直接 `rmtree(target)` 再复制，复制中途失败就两个版本都没了；
   必须先装到 `.incoming-<v>` 再 rename（Windows 同卷 rename 基本原子）。
3. **zip 可能多套一层目录**：PyInstaller 打包目录里是 `mascot/mascot.exe`，解压后要往下找一层。
4. **升级前必须停实例**：Windows 上正在运行的 exe 被锁，直接覆盖会 `Access denied`；
   这也解释了 install-win.sh 里的 `ctl stop` + `sleep 1`。

## 遗留

- 仍无网络自动更新（没有清单服务器）与签名校验；
- `update` 只支持本地目录/zip，不支持 MSI；
- 升级后不自动拉起新版本（提示用户 `mascot.exe run`）；
- install-win.sh 仍是「首次安装/开发部署」的引导脚本，`update` 面向已安装的 exe。
