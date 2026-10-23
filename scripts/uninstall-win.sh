#!/usr/bin/env bash
# 卸载：停实例 → 关自启 → 只删本程序自己的版本目录。
# 默认保留 state/log（%LOCALAPPDATA%\mascot 下其它内容），--all 才整体删除。
set -euo pipefail

WIN_ROOT=${WIN_ROOT:-/mnt/c/Users/Public/mascot}
VERSION=${VERSION:-0.1.0}
PY="$WIN_ROOT/venv/Scripts/python.exe"
LOCAL_WIN="$("$PY" -c 'import os,sys;sys.stdout.write(os.environ["LOCALAPPDATA"])')"
LOCAL="$(wslpath -u "$LOCAL_WIN")/mascot"
DEST="$LOCAL/app/$VERSION"

EXE="$DEST/mascot.exe"
if [ -x "$EXE" ]; then
  "$EXE" ctl stop >/dev/null 2>&1 || true
  "$EXE" autostart off >/dev/null 2>&1 || true
fi

# 先删开始菜单项（它指向的就是要删掉的 exe）
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$HERE/make-shortcut.ps1")" \
    -Target "$LOCAL_WIN\\mascot\\app\\$VERSION\\mascot.exe" -Remove 2>/dev/null | tr -d '\r' | sed 's/^/   /'
fi

echo "== 删除 $DEST"
rm -rf "$DEST"

# 指针不能指向已删除的版本：current.txt 还指它就先摘掉
if [ -f "$LOCAL/current.txt" ] && [ "$(cat "$LOCAL/current.txt")" = "$VERSION" ]; then
  rm -f "$LOCAL/current.txt"
fi
rmdir "$LOCAL/app" 2>/dev/null || true

if [ "${1:-}" = "--all" ]; then
  echo "== 删除整个 $LOCAL（含日志与状态）"
  rm -rf "$LOCAL"
fi
echo "== done"
