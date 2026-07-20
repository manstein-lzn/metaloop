from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "metaloop_core"
SKILL = ROOT / "skills" / "metaloop"

EXPECTED_CORE = {
    "__init__.py",
    "cli.py",
    "contracts.py",
    "decisions.py",
    "durable.py",
    "host.py",
    "recovery.py",
    "schemas.py",
    "verification.py",
    "workspace.py",
}
REMOVED_COMMANDS = {"design", "run", "migrate-legacy", "tick", "relay", "activate"}
REMOVED_ACTIVE_TERMS = {"Mission Capsule", "legacy_unbound", "V1 compatibility", "V2 compatibility"}


def main() -> int:
    errors: list[str] = []
    core_files = {path.name for path in CORE.glob("*.py")}
    vendored_files = {path.name for path in (SKILL / "lib" / "metaloop_core").glob("*.py")}
    if core_files != EXPECTED_CORE:
        errors.append(f"canonical core surface mismatch: {sorted(core_files ^ EXPECTED_CORE)}")
    if vendored_files != EXPECTED_CORE:
        errors.append(f"vendored core surface mismatch: {sorted(vendored_files ^ EXPECTED_CORE)}")
    cli = (CORE / "cli.py").read_text(encoding="utf-8")
    for command in REMOVED_COMMANDS:
        if f'add_parser("{command}"' in cli:
            errors.append(f"removed command is still registered: {command}")
    if 'commands.add_parser("verify"' in cli:
        errors.append("removed top-level command is still registered: verify")
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for term in REMOVED_ACTIVE_TERMS:
        if term in skill:
            errors.append(f"removed active term remains in Skill: {term}")
    refs = {path.name for path in (SKILL / "references").glob("*") if path.is_file()}
    if refs != {"final_protocol.md", "prompt_first_code_backed.md"}:
        errors.append(f"active references mismatch: {sorted(refs)}")
    if (SKILL / "extensions").exists() and any(path.is_file() for path in (SKILL / "extensions").rglob("*")):
        errors.append("legacy extensions directory remains in active Skill")
    scripts = {path.name for path in (SKILL / "scripts").glob("*.py")}
    if scripts != {"metaloop_kernel.py"}:
        errors.append(f"active scripts mismatch: {sorted(scripts)}")
    if errors:
        print("v3 surface check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("v3 surface ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
