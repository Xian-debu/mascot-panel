"""生成/更新渲染快照基线，并输出一张暗底拼图供人工检查。

用法（仓库根目录）：
    uv run python scripts/make_baselines.py            # 写入 tests/snapshot/baseline/
    uv run python scripts/make_baselines.py --check    # 只报告差异，不写
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mascot_render.gallery import contact_sheet, snapshot_cases  # noqa: E402

BASELINE = ROOT / "tests" / "snapshot" / "baseline"
EVIDENCE = ROOT / "evidence"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只对比，不写文件")
    args = ap.parse_args()

    BASELINE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    cases = snapshot_cases()
    changed = []
    for name, img in cases.items():
        path = BASELINE / f"{name}.png"
        if args.check:
            if not path.exists():
                changed.append(f"missing {name}")
            continue
        img.save(path)
    if not args.check:
        sheet = contact_sheet()
        sheet.save(EVIDENCE / "m3-render-gallery.png")
        print(f"wrote {len(cases)} baselines to {BASELINE}")
        print(f"gallery: {EVIDENCE / 'm3-render-gallery.png'}")
    if changed:
        print("\n".join(changed))
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
