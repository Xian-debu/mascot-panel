#!/usr/bin/env bash
# 在 Windows 开发副本里跑 PyInstaller，产出 onedir 发行版。
#
#   WIN_ROOT=/mnt/c/Users/Public/mascot bash scripts/build-win.sh
#
# 为什么要先 deploy：Windows 侧只能读 /mnt/c（WSL ext4 对 Windows 进程不可见），
# 所以构建的源码树是"发布到 Windows 的那一份"，而不是 /root/mascot 本体。
set -euo pipefail

WIN_ROOT=${WIN_ROOT:-/mnt/c/Users/Public/mascot}
VERSION=${VERSION:-0.1.1}
APP_DIR="$WIN_ROOT/app/$VERSION"
DIST_DIR="$WIN_ROOT/dist"
BUILD_DIR="$WIN_ROOT/build"
PY="$WIN_ROOT/venv/Scripts/python.exe"

if [ ! -x "$PY" ]; then
  echo "missing $PY (先建 Windows venv)" >&2
  exit 3
fi

echo "== 1/2 deploy $VERSION -> $APP_DIR"
WIN_ROOT="$WIN_ROOT" bash "$(dirname "$0")/deploy-win.sh"

echo "== 2/2 pyinstaller"
rm -rf "$DIST_DIR/mascot" "$BUILD_DIR/mascot"
cd "$APP_DIR"
# Windows 进程看不懂 /mnt/c：所有路径必须转成 C:\ 形式
WIN_DIST=$(wslpath -w "$DIST_DIR")
WIN_BUILD=$(wslpath -w "$BUILD_DIR")
WIN_SPEC=$(wslpath -w "$APP_DIR/packaging/mascot.spec")
"$PY" -m PyInstaller \
  --noconfirm --clean \
  --distpath "$WIN_DIST" \
  --workpath "$WIN_BUILD" \
  "$WIN_SPEC"

echo "== done: $DIST_DIR/mascot/mascot.exe"
ls -lh "$DIST_DIR/mascot/mascot.exe"
