from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "metaloop_core"
TARGET = ROOT / "skills" / "metaloop" / "lib" / "metaloop_core"


def main() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, TARGET, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"synced {SOURCE} -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
