"""已安装版本目录的列举与回收（纯逻辑，不碰 Win32）。

安装布局（docs/19-m5-delivery.md）：
    %LOCALAPPDATA%/mascot/
        current.txt          # 只有一行版本号
        app/<version>/...    # 每个版本一个不可变目录
        rollback.bat

版本目录只增不减会一直吃盘（每个版本约 8MB），这里提供：
- list_versions: 列出 app/ 下所有版本目录、大小、哪个是 current；
- pick_prune:    决定保留哪些、删哪些（current 永不删，keep 是保留总数）；
- prune_versions: 真正删除（默认 dry_run）。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,3}(?:[-+][0-9A-Za-z][0-9A-Za-z.\-]*)?$")
CURRENT_FILE = "current.txt"


def is_version_name(name: str) -> bool:
    """目录名是否像版本号（0.1.0、1.2、1.0.0-beta.1）。"""
    return bool(VERSION_RE.match(name))


def version_key(name: str) -> tuple[int, ...]:
    """把版本号转成可排序的整数元组；非数字段（-beta）按 0 处理。"""
    head = name.split("-", 1)[0].split("+", 1)[0]
    parts = [int(p) for p in head.split(".") if p.isdigit()]
    return tuple(parts + [0] * (4 - len(parts)))[:4]


def read_current(app_dir: Path) -> str | None:
    """读 current.txt；不存在或内容不像版本号时返回 None。"""
    try:
        text = (app_dir.parent / CURRENT_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if is_version_name(text) else None


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def list_versions(app_dir: Path) -> list[dict]:
    """列出 app_dir 下的版本目录，按版本号从新到旧。"""
    current = read_current(app_dir)
    rows: list[dict] = []
    try:
        entries = sorted(app_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        return rows
    for entry in entries:
        if not entry.is_dir() or not is_version_name(entry.name):
            continue
        rows.append(
            {
                "version": entry.name,
                "path": str(entry),
                "size_bytes": _dir_size(entry),
                "current": entry.name == current,
            }
        )
    rows.sort(key=lambda row: version_key(str(row["version"])), reverse=True)
    return rows


def pick_prune(rows: list[dict], keep: int = 2, current: str | None = None) -> list[str]:
    """返回要删除的版本号：current 必留，其余按新到旧留满 keep 个。"""
    keep = max(1, keep)
    names = [str(row["version"]) for row in rows]
    ordered = sorted(names, key=version_key, reverse=True)
    keep_set: set[str] = set()
    if current in names:
        keep_set.add(str(current))
    for name in ordered:
        if len(keep_set) >= keep:
            break
        keep_set.add(name)
    return [name for name in ordered if name not in keep_set]


def prune_versions(app_dir: Path, keep: int = 2, dry_run: bool = True) -> dict:
    """回收旧版本目录；返回删除清单与释放的字节数。"""
    rows = list_versions(app_dir)
    doomed = pick_prune(rows, keep=keep, current=read_current(app_dir))
    freed = 0
    removed: list[str] = []
    kept = [str(row["version"]) for row in rows if str(row["version"]) not in doomed]
    for row in rows:
        name = str(row["version"])
        if name not in doomed:
            continue
        target = Path(str(row["path"]))
        # 双保险：只删 app_dir 下、名字像版本号的目录
        if target.parent.resolve() != app_dir.resolve() or not is_version_name(target.name):
            continue
        freed += int(row["size_bytes"])
        if dry_run:
            removed.append(name)
            continue
        shutil.rmtree(target, ignore_errors=True)
        removed.append(name)
    return {
        "app_dir": str(app_dir),
        "current": read_current(app_dir),
        "keep": max(1, keep),
        "dry_run": dry_run,
        "kept": kept,
        "removed": removed,
        "freed_bytes": freed,
    }
