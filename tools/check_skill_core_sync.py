from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "metaloop_core"
TARGET = ROOT / "skills" / "metaloop" / "lib" / "metaloop_core"


def _files(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def main() -> int:
    source = _files(SOURCE)
    target = _files(TARGET)
    if source == target:
        print("skill core sync ok")
        return 0
    missing = sorted(source.keys() - target.keys())
    extra = sorted(target.keys() - source.keys())
    changed = sorted(name for name in source.keys() & target.keys() if source[name] != target[name])
    for label, names in [("missing", missing), ("extra", extra), ("changed", changed)]:
        for name in names:
            print(f"{label}: {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
