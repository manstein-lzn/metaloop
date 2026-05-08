from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_metaloop_skill_declares_entry_and_enforcement_boundary() -> None:
    skill = (ROOT / "skills" / "metaloop" / "SKILL.md").read_text(encoding="utf-8")
    openai_yaml = (ROOT / "skills" / "metaloop" / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "name: metaloop" in skill
    assert "scripts/metaloop_kernel.py" in skill
    assert "do not assume a separate `metaloop` package is installed" in skill
    assert "MetaLoop is skill-first, not prompt-only." in skill
    assert "Skill handles entry and alignment." in skill
    assert "bundled kernel for state and checks" in skill
    assert "Hooks, sandbox, or wrapper runtime handle stronger non-bypassable constraints" in skill
    assert "Do not silently change a locked MissionSpec" in skill
    assert 'display_name: "MetaLoop"' in openai_yaml
    assert 'default_prompt: "Use $metaloop' in openai_yaml


def test_metaloop_skill_reference_captures_lightweight_protocol() -> None:
    reference = (ROOT / "skills" / "metaloop" / "references" / "lightweight_protocol.md").read_text(encoding="utf-8")

    assert "Codex's task design and stable execution protocol layer" in reference
    assert "$metaloop skill" in reference
    assert "Bundled scripts / schemas / validators" in reference
    assert "hooks / sandbox / wrapper runtime" in reference
    assert "must not require the target machine to have the MetaLoop repository installed" in reference
    assert "repair" in reference
    assert "redesign" in reference


def test_bundled_skill_kernel_design_status_and_verify(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    target = tmp_path / "result.txt"

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Create result.txt",
            "--rationale",
            "File output is the smallest verifiable artifact.",
            "--non-goal",
            "Do not create unrelated files.",
            "--file-exists",
            "result.txt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert design.returncode == 0
    assert (tmp_path / ".metaloop" / "mission_capsule.json").exists()

    first_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert first_verify.returncode == 1
    assert "verification: failed" in first_verify.stdout

    target.write_text("done\n", encoding="utf-8")
    second_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert second_verify.returncode == 0
    assert "verification: completed_verified" in second_verify.stdout
    assert (tmp_path / ".metaloop" / "verification_result.json").exists()


def test_bundled_skill_kernel_does_not_hard_verify_manual_only_acceptance(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    target = tmp_path / "review.txt"

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--acceptance",
            "User confirms the result is useful.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert verify.returncode == 1
    assert "verification: missing_verification_plan" in verify.stdout

    status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0
    assert "next_action: Add executable validators" in status.stdout

    target.write_text("ready for review\n", encoding="utf-8")
    design_with_hard_validator = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--acceptance",
            "User confirms the result is useful.",
            "--file-exists",
            "review.txt",
            "--force",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design_with_hard_validator.returncode == 0

    verify_with_manual_acceptance = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify_with_manual_acceptance.returncode == 1
    assert "verification: human_acceptance_required" in verify_with_manual_acceptance.stdout
