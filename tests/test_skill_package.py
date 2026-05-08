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
    assert "ExtensionSpec" in skill
    assert "mode" in skill
    assert "severity" in skill
    assert "extensions/generic/examples/basic.json" in skill
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
    assert "ExtensionSpec" in reference
    assert "Manual or unsupported blocking checks" in reference
    assert "extensions/<domain>/" in reference


def test_metaloop_skill_contains_generic_extension_package() -> None:
    profile = json.loads((ROOT / "skills" / "metaloop" / "extensions" / "generic" / "profile.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "skills" / "metaloop" / "extensions" / "generic" / "verification_schema.json").read_text(encoding="utf-8"))
    example = json.loads((ROOT / "skills" / "metaloop" / "extensions" / "generic" / "examples" / "basic.json").read_text(encoding="utf-8"))

    assert profile["domain"] == "generic"
    assert any(item["type"] == "json_metric_gate" for item in profile["validator_types"])
    assert schema["validator_fields"]["resource_gate"]
    assert example["extension_spec"]["schema"] == "metaloop.extension_spec"


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
    assert "at least one executable validator" in manual_only_without_override.stderr

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

    redesign_without_reason = subprocess.run(
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
    assert redesign_without_reason.returncode == 1
    assert "revision_reason_required" in redesign_without_reason.stderr

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
            "--revision-reason",
            "Add executable file validation to the locked contract.",
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


def test_bundled_skill_kernel_extension_spec_modes_and_revision(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    extension_path = tmp_path / "extension.json"
    verification_path = tmp_path / "verification.json"
    extension_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.extension_spec",
                "version": "1.0",
                "domain": "experiment_safety",
                "purpose": "Capture experiment-specific safety gates.",
                "validator_types": [{"type": "domain_manual_gate", "mode": "manual"}],
                "risk_checks": ["Check promotion claims and resource use."],
                "review_questions": ["Are subset-only claims blocked?"],
                "known_gaps": ["No automated domain reviewer is installed."],
            }
        ),
        encoding="utf-8",
    )
    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "experiment_safety",
                "extension": "experiment_safety",
                "extension_version": "1.0",
                "validators": [
                    {"type": "domain_manual_gate", "mode": "manual", "severity": "blocking", "description": "Manual promotion claim review."}
                ],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Review an experiment promotion",
            "--rationale",
            "Domain claims need task-specific review.",
            "--non-goal",
            "Do not hard-verify unavailable domain judgment.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
            "--allow-manual-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert capsule["extension_spec"]["domain"] == "experiment_safety"
    assert capsule["extension_spec"]["extension_hash"].startswith("sha256:")

    run = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "run", "--command", "true"],
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
    assert verify.returncode == 1
    result = json.loads(verify.stdout)
    assert result["status"] == "human_acceptance_required"
    assert result["manual_validator_results"][0]["type"] == "domain_manual_gate"
    assert result["warnings"][0]["type"] == "known_gap"

    capsule["extension_spec"]["purpose"] = "tampered"
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    tampered = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tampered.returncode == 1
    assert "verification: invalid_capsule" in tampered.stdout

    fixed_design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Review an experiment promotion with an executable artifact",
            "--rationale",
            "Add a concrete artifact gate.",
            "--non-goal",
            "Do not overwrite without revision history.",
            "--file-exists",
            "report.txt",
            "--force",
            "--revision-reason",
            "Replace tampered capsule with executable revision.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert fixed_design.returncode == 0
    assert (tmp_path / ".metaloop" / "revisions").exists()
    revised = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert revised["revision"] == 2
    assert revised["previous_capsule_id"]


def test_bundled_skill_kernel_generic_validator_modes(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("required text\n", encoding="utf-8")
    digest = "sha256:" + __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()
    advisory = json.dumps({"type": "file_contains", "mode": "executable", "severity": "advisory", "path": "artifact.txt", "contains": "missing advisory text"})
    resource_gate = json.dumps({"type": "resource_gate", "mode": "manual", "severity": "blocking", "resource": "gpu", "requires_user_confirmation": True})

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Validate generic artifacts and resource gates",
            "--rationale",
            "Generic validators should compose across domains.",
            "--non-goal",
            "Do not treat resource approval as hard verified.",
            "--file-contains",
            json.dumps({"path": "artifact.txt", "contains": "required text"}),
            "--json-field-exists",
            json.dumps({"path": "summary.json", "field": "held_out.peak1_delta"}),
            "--artifact-hash",
            json.dumps({"path": "artifact.txt", "sha256": digest}),
            "--validator",
            advisory,
            "--resource-gate",
            resource_gate,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    run = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "run",
            "--command",
            "printf '{\"held_out\":{\"peak1_delta\":0}}' > summary.json",
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
    assert verify.returncode == 1
    result = json.loads(verify.stdout)
    assert result["status"] == "human_acceptance_required"
    assert result["manual_validator_results"][0]["type"] == "resource_gate"
    assert any(item["type"] == "file_contains" for item in result["warnings"])

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    capsule["verification_spec"]["resource_gates"] = []
    capsule["verification_spec"]["spec_hash"] = _test_hash(capsule["verification_spec"], "spec_hash")
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")

    automated_verify = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "verify", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert automated_verify.returncode == 0
    automated_result = json.loads(automated_verify.stdout)
    assert automated_result["status"] == "completed_verified"


def test_bundled_skill_kernel_rejects_malformed_and_out_of_language_specs(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    extension_path = tmp_path / "extension.json"
    verification_path = tmp_path / "verification.json"
    extension_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.extension_spec",
                "version": "1.0",
                "domain": "review_domain",
                "purpose": "Strict review language.",
                "validator_types": [{"type": "domain_gate", "mode": "manual"}],
                "risk_checks": ["Check malformed specs."],
                "review_questions": [],
                "known_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "review_domain",
                "extension": "review_domain",
                "extension_version": "1.0",
                "validators": [{"type": "domain_gate", "mode": "bogus", "severity": "blocking"}],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )
    malformed = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Reject malformed validator mode",
            "--rationale",
            "Locked specs must be explicit.",
            "--non-goal",
            "Do not infer invalid validator metadata.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
            "--allow-manual-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert malformed.returncode == 1
    assert "mode must be one of" in malformed.stderr

    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "review_domain",
                "extension": "review_domain",
                "extension_version": "1.0",
                "validators": [{"type": "file_exists", "mode": "executable", "severity": "blocking", "path": "x"}],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )
    out_of_language = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Reject validators outside the extension language",
            "--rationale",
            "ExtensionSpec defines the locked verification language.",
            "--non-goal",
            "Do not bypass domain extension declarations.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert out_of_language.returncode == 1
    assert "type is not declared by extension_spec.validator_types" in out_of_language.stderr


def test_bundled_skill_kernel_reports_declared_but_unimplemented_executable_as_unsupported(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    extension_path = tmp_path / "extension.json"
    verification_path = tmp_path / "verification.json"
    extension_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.extension_spec",
                "version": "1.0",
                "domain": "future_domain",
                "purpose": "Declare a future executable validator.",
                "validator_types": [{"type": "future_gate", "mode": "executable"}],
                "risk_checks": ["Check unsupported executable support before completion."],
                "review_questions": [],
                "known_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    verification_path.write_text(
        json.dumps(
            {
                "schema": "metaloop.verification_spec",
                "version": "1.0",
                "domain": "future_domain",
                "extension": "future_domain",
                "extension_version": "1.0",
                "validators": [
                    {"type": "future_gate", "mode": "executable", "severity": "blocking", "description": "Future executable gate."}
                ],
                "evidence_requirements": [],
                "resource_gates": [],
            }
        ),
        encoding="utf-8",
    )

    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Lock a declared but unavailable validator",
            "--rationale",
            "The verifier must not pretend unsupported executables passed.",
            "--non-goal",
            "Do not mark unsupported validators completed.",
            "--extension-spec",
            str(extension_path),
            "--verification-spec",
            str(verification_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0
    run = subprocess.run(
        [sys.executable, str(kernel), "--workspace", str(tmp_path), "run", "--command", "true"],
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
    assert verify.returncode == 1
    result = json.loads(verify.stdout)
    assert result["status"] == "unsupported_verification_spec"
    assert result["unsupported_validator_results"][0]["type"] == "future_gate"


def test_bundled_skill_kernel_sanitizes_revision_archive_filename(tmp_path) -> None:
    kernel = ROOT / "skills" / "metaloop" / "scripts" / "metaloop_kernel.py"
    design = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Create initial capsule",
            "--rationale",
            "Revision archive behavior must be safe.",
            "--non-goal",
            "Do not trust old capsule filenames.",
            "--file-exists",
            "result.txt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert design.returncode == 0

    capsule_path = tmp_path / ".metaloop" / "mission_capsule.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    capsule["capsule_id"] = "../escape/capsule"
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    revised = subprocess.run(
        [
            sys.executable,
            str(kernel),
            "--workspace",
            str(tmp_path),
            "design",
            "--intent",
            "Create revised capsule",
            "--rationale",
            "Archive filenames must be sanitized.",
            "--non-goal",
            "Do not write revision files outside .metaloop/revisions.",
            "--file-exists",
            "result.txt",
            "--force",
            "--revision-reason",
            "Exercise archive sanitization.",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert revised.returncode == 0
    revisions = list((tmp_path / ".metaloop" / "revisions").glob("*.json"))
    assert len(revisions) == 1
    assert revisions[0].parent == tmp_path / ".metaloop" / "revisions"
    assert ".." not in revisions[0].name
    assert "escape_capsule" in revisions[0].name
    assert not (tmp_path / ".metaloop" / "escape").exists()


def _test_hash(payload: dict, hash_key: str) -> str:
    normalized = dict(payload)
    normalized.pop(hash_key, None)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + __import__("hashlib").sha256(encoded).hexdigest()
