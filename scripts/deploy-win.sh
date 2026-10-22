#!/usr/bin/env bash
# 把本仓库发布到 Windows 开发副本：C:/Users/Public/mascot/app/<version>/
# 版本化目录 + current.txt 指针，失败不写指针（照 win-admin 的双包模型）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_ROOT="${WIN_ROOT:-/mnt/c/Users/Public/mascot}"
VERSION="$(cd "$ROOT" && uv run python -c 'import mascot_app; print(mascot_app.__version__)')"
DEST="$WIN_ROOT/app/$VERSION"

if [ ! -d /mnt/c/Users/Public ]; then
  echo "ERR: /mnt/c/Users/Public 不存在（不在 WSL 或 C: 未挂载）" >&2
  exit 3
fi

mkdir -p "$DEST"
# 只同步源码与元数据，不带 .venv / 测试缓存
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude 'logs' \
  "$ROOT/" "$DEST/"

# 清单：每个文件的 sha256，供 Windows 侧核对
( cd "$DEST" && find . -type f ! -name 'MANIFEST.sha256' -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256 )

# 最后写指针：中途失败不会留下"指向不完整目录"的 current.txt
printf '%s' "$VERSION" > "$WIN_ROOT/current.txt.tmp"
mv "$WIN_ROOT/current.txt.tmp" "$WIN_ROOT/current.txt"

echo "deployed $VERSION -> $DEST"
echo "current -> $(cat "$WIN_ROOT/current.txt")"
