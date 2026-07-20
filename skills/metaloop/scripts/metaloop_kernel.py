#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
VENDORED_LIB = SKILL_ROOT / "lib"
if str(VENDORED_LIB) not in sys.path:
    sys.path.insert(0, str(VENDORED_LIB))

from metaloop_core.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
