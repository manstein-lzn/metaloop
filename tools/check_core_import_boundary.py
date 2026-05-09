from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_CORE_IMPORTS = {
    "metaloop.cli",
    "metaloop.ui",
    "metaloop.tui_shell",
    "metaloop.codex_adapter",
    "metaloop.goal_runtime",
    "metaloop.user_agent",
    "metaloop.agents",
    "metaloop.workers",
}


def main() -> int:
    core_root = Path("src/metaloop_core")
    for path in core_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name in FORBIDDEN_CORE_IMPORTS:
                    print(f"forbidden core import in {path}: {name}")
                    return 1
    print("core import boundary ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
