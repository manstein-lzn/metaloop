from pathlib import Path
import json
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
    assert "run" in skill
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
    assert "verification: missing_execution_report" in first_verify.stdout

    run = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf 'done\\n' > result.txt",
            "--evidence",
            "result.txt was created by the run wrapper.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0
    assert "execution: completed" in run.stdout
    assert target.read_text(encoding="utf-8") == "done\n"
    assert (tmp_path / ".metaloop" / "execution_report.json").exists()

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

    shallow_design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert shallow_design.returncode == 1
    assert "at least one --rationale" in shallow_design.stderr

    manual_only_without_override = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--rationale",
            "Human usefulness is the core acceptance boundary.",
            "--non-goal",
            "Do not claim automated completion.",
            "--acceptance",
            "User confirms the result is useful.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert manual_only_without_override.returncode == 1
    assert "at least one hard validator" in manual_only_without_override.stderr

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--rationale",
            "Human usefulness is the core acceptance boundary.",
            "--non-goal",
            "Do not claim automated completion.",
            "--acceptance",
            "User confirms the result is useful.",
            "--allow-manual-only",
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
    assert "verification: missing_execution_report" in verify.stdout

    status = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0
    assert "next_action: Run execution through the lightweight kernel" in status.stdout

    design_with_hard_validator = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Produce a result that needs human review",
            "--rationale",
            "Human usefulness is the core acceptance boundary.",
            "--non-goal",
            "Do not claim automated completion.",
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

    run_with_manual_acceptance = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf 'ready for review\\n' > review.txt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run_with_manual_acceptance.returncode == 0
    assert target.read_text(encoding="utf-8") == "ready for review\n"

    verify_with_manual_acceptance = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify_with_manual_acceptance.returncode == 1
    assert "verification: human_acceptance_required" in verify_with_manual_acceptance.stdout


def test_bundled_skill_kernel_supports_locked_json_metric_verification_spec(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    gate = json.dumps({"path": "summary.json", "metric": "held_out.peak1_delta", "operator": ">=", "threshold": 0})

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Write a summary with a non-regressing held-out metric",
            "--rationale",
            "The metric gate is the locked completion definition.",
            "--non-goal",
            "Do not claim completion from a missing summary.",
            "--json-metric-gate",
            gate,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    spec = capsule["verification_spec"]
    assert spec["schema"] == "metaloop.verification_spec"
    assert spec["domain"] == "generic"
    assert spec["extension_hash"].startswith("sha256:")
    assert spec["validators"][0]["type"] == "json_metric_gate"

    run = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf '{\"held_out\":{\"peak1_delta\":0.1}}' > summary.json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0

    verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 0
    result = json.loads(verify.stdout)
    assert result["status"] == "completed_verified"
    assert result["verification_spec_domain"] == "generic"
    assert result["extension_hash"] == spec["extension_hash"]
    assert result["hard_validator_results"][0]["actual"] == 0.1

    capsule["verification_spec"]["validators"][0]["threshold"] = 1
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    tampered_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tampered_verify.returncode == 1
    assert "verification: invalid_capsule" in tampered_verify.stdout
