from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from metaloop_core.host import safe_point


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_core_is_the_only_packaged_implementation() -> None:
    expected = {"__init__.py", "cli.py", "contracts.py", "decisions.py", "durable.py", "host.py", "recovery.py", "schemas.py", "verification.py", "workspace.py"}
    source = {path.name for path in (ROOT / "src" / "metaloop_core").glob("*.py")}
    vendored = {path.name for path in (ROOT / "skills" / "metaloop" / "lib" / "metaloop_core").glob("*.py")}
    assert source == vendored == expected
    for name in expected:
        assert (ROOT / "src" / "metaloop_core" / name).read_bytes() == (ROOT / "skills" / "metaloop" / "lib" / "metaloop_core" / name).read_bytes()


def test_portable_kernel_is_a_thin_standard_library_bootstrap() -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    source = kernel.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 30
    assert "from metaloop_core.cli import main" in source
    result = subprocess.run([sys.executable, "-m", "py_compile", str(kernel)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_active_skill_and_docs_describe_v3_only() -> None:
    skill = (ROOT / "skills" / "metaloop" / "SKILL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    charter = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "MetaLoop v3.2" in skill
    assert all(word in skill for word in ["Frame", "Work", "Reconcile", "Adapt", "Prove", "WorkspaceStamp", "atomic_direct", "high_assurance", "fresh-context"])
    assert "MetaLoop v3.2" in readme
    assert "MetaLoop 是一个极小、正交、事件触发的外环控制系统" in charter
    assert "默认信任 Agent" in charter
    for removed in ["Mission Capsule", "migrate-legacy", "legacy_unbound", "V1 compatibility", "V2 compatibility"]:
        assert removed not in skill
    assert not (ROOT / "skills" / "metaloop" / "references" / "legacy_v1_compatibility.md").exists()
    assert not (ROOT / "skills" / "metaloop" / "references" / "v2_governance.md").exists()


def test_optional_host_safe_point_is_synchronous_and_read_only(tmp_path: Path) -> None:
    source = (ROOT / "src" / "metaloop_core" / "host.py").read_text(encoding="utf-8")
    assert "daemon" not in source.lower()
    assert "thread" not in source.lower()
    assert "subprocess" not in source
    assert callable(safe_point)


def test_surface_audit_script_passes() -> None:
    result = subprocess.run([sys.executable, "tools/check_v3_surface.py"], cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
