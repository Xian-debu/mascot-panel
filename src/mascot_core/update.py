"""就地升级（M23）：从本地目录或 zip 安装新版本，原子切 current.txt，保留回滚目标。

纯逻辑：不启动/停止进程、不弹窗、不写注册表。CLI 负责停实例与版本号推断。
目录模型沿用 M18：版本目录不可变，current.txt 是唯一指针，升级 = 新目录 + 改指针。
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from mascot_core.versions import (
    CURRENT_FILE,
    is_version_name,
    pick_prune,
    prune_versions,
    version_key,
)

EXE_NAME = "mascot.exe"
TMP_PREFIX = ".incoming-"


def source_kind(source: Path) -> str:
    """判断升级源是目录还是 zip；不合法时抛 ValueError。"""
    if source.is_dir():
        if not (source / EXE_NAME).is_file():
            raise ValueError(f"目录里没有 {EXE_NAME}：{source}")
        return "dir"
    if source.is_file() and source.suffix.lower() == ".zip":
        return "zip"
    raise ValueError(f"升级源必须是含 {EXE_NAME} 的目录或 .zip 文件：{source}")


def _safe_extract(zip_path: Path, dest: Path) -> None:
    """解压到 dest，拒绝 ../ 与绝对路径（zip slip）。"""
    root = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            name = member.filename
            if not name or name.endswith("/"):
                continue
            target = (dest / name).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"zip 里有越界路径：{name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _locate_exe_root(extracted: Path) -> Path:
    """解压结果可能直接含 exe，也可能多套一层目录；找到含 exe 的那层。"""
    if (extracted / EXE_NAME).is_file():
        return extracted
    for child in extracted.iterdir():
        if child.is_dir() and (child / EXE_NAME).is_file():
            return child
    raise ValueError(f"zip 里没有 {EXE_NAME}")


def _write_current(app_dir: Path, version: str) -> None:
    ptr = app_dir.parent / CURRENT_FILE
    tmp = ptr.with_suffix(".txt.tmp")
    tmp.write_text(version + chr(10), encoding="utf-8")
    tmp.replace(ptr)


def install(
    source: Path,
    app_dir: Path,
    version: str,
    *,
    keep: int = 2,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """安装 source 为 app_dir/<version> 并切换 current.txt。

    返回计划/结果（JSON 友好）；dry_run 时不落盘、不切换。
    同一版本已存在时要求 force=True（覆盖安装）。
    """
    if not is_version_name(version):
        raise ValueError(f"版本号不合法：{version!r}")
    kind = source_kind(source)
    app_dir = app_dir.resolve()
    target = app_dir / version
    ptr = app_dir.parent / CURRENT_FILE
    previous = ptr.read_text(encoding="utf-8").strip() if ptr.is_file() else ""
    if target.exists() and not force:
        raise ValueError(f"{version} 已安装；要覆盖请加 --force")

    # 计划里把 target 也算进去，dry-run 才能报出「装完会删掉谁」
    rows = [{"version": p.name} for p in app_dir.iterdir() if p.is_dir() and is_version_name(p.name)] if app_dir.is_dir() else []
    if not any(r["version"] == version for r in rows):
        rows.append({"version": version})
    rows.sort(key=lambda r: version_key(str(r["version"])), reverse=True)
    remove = pick_prune(rows, keep=keep, current=version)
    result: dict = {
        "source": str(source),
        "kind": kind,
        "version": version,
        "app_dir": str(app_dir),
        "target": str(target),
        "previous": previous,
        "dry_run": dry_run,
        "installed": False,
        "would_remove": remove,
    }
    if dry_run:
        return result

    app_dir.mkdir(parents=True, exist_ok=True)
    incoming = app_dir / (TMP_PREFIX + version)
    if incoming.exists():
        shutil.rmtree(incoming)
    try:
        if kind == "dir":
            shutil.copytree(source, incoming)
        else:
            incoming.mkdir(parents=True)
            _safe_extract(source, incoming)
            inner = _locate_exe_root(incoming)
            if inner != incoming:
                promoted = app_dir / (TMP_PREFIX + version + "-x")
                if promoted.exists():
                    shutil.rmtree(promoted)
                inner.rename(promoted)
                shutil.rmtree(incoming)
                promoted.rename(incoming)
        if not (incoming / EXE_NAME).is_file():
            raise ValueError(f"升级源里没有 {EXE_NAME}")
        if target.exists():
            shutil.rmtree(target)
        incoming.rename(target)
    except Exception:
        shutil.rmtree(incoming, ignore_errors=True)
        raise

    _write_current(app_dir, version)
    pruned = prune_versions(app_dir, keep=keep, dry_run=False)
    result["installed"] = True
    result["removed"] = pruned.get("removed", [])
    result["freed_bytes"] = pruned.get("freed_bytes", 0)
    result["current"] = version
    return result
