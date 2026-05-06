from pathlib import Path

import pytest

from metaloop.prompt_pack import PromptPackError, load_prompt_template, render_prompt


def _write_prompt(path: Path, *, body: str = "Hello {{name}}\n", required_variables: str = "[name]") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "id: test.example",
                "stage: test",
                "version: 1",
                "purpose: Test prompt rendering.",
                "input_schema: TestInput",
                "output_schema: TestOutput",
                "failure_policy: Fail fast.",
                f"required_variables: {required_variables}",
                "---",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def test_prompt_pack_parses_metadata(tmp_path) -> None:
    _write_prompt(tmp_path / "prompts" / "example.md", required_variables="name, details")

    template = load_prompt_template("example", prompt_root=tmp_path)

    assert template.prompt_id == "test.example"
    assert template.version == "1"
    assert template.metadata["stage"] == "test"
    assert template.required_variables == ("name", "details")


def test_prompt_pack_renders_successfully(tmp_path) -> None:
    _write_prompt(tmp_path / "prompts" / "example.md", body="Hello {{name}}\nDetails:\n{{details}}\n", required_variables="[\"name\", \"details\"]")

    rendered = render_prompt("example", {"name": "MetaLoop", "details": "structured state"}, prompt_root=tmp_path)

    assert rendered.rendered_text == "Hello MetaLoop\nDetails:\nstructured state"
    assert rendered.prompt_id == "test.example"
    assert rendered.sha256 == rendered.hash


def test_prompt_pack_missing_file_fails(tmp_path) -> None:
    with pytest.raises(PromptPackError, match="prompt file not found"):
        render_prompt("missing", {}, prompt_root=tmp_path)


def test_prompt_pack_missing_required_metadata_fails(tmp_path) -> None:
    path = tmp_path / "prompts" / "bad.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "version: 1",
                "purpose: Missing schema fields.",
                "---",
                "",
                "Hello {{name}}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(PromptPackError, match="prompt metadata missing required fields"):
        render_prompt("bad", {"name": "MetaLoop"}, prompt_root=tmp_path)


def test_prompt_pack_missing_required_variable_fails(tmp_path) -> None:
    _write_prompt(tmp_path / "prompts" / "example.md")

    with pytest.raises(PromptPackError, match="missing required variable: name"):
        render_prompt("example", {}, prompt_root=tmp_path)


def test_prompt_pack_empty_required_variable_fails(tmp_path) -> None:
    _write_prompt(tmp_path / "prompts" / "example.md")

    with pytest.raises(PromptPackError, match="empty variable value: name"):
        render_prompt("example", {"name": "   "}, prompt_root=tmp_path)


def test_prompt_pack_call_site_required_variables_are_enforced(tmp_path) -> None:
    _write_prompt(tmp_path / "prompts" / "example.md", body="No template slots\n", required_variables="")

    with pytest.raises(PromptPackError, match="missing required variable: mission_spec"):
        render_prompt("example", {}, prompt_root=tmp_path, required_variables=["mission_spec"])

    rendered = render_prompt("example", {"mission_spec": "{}"}, prompt_root=tmp_path, required_variables=["mission_spec"])

    assert rendered.rendered_text == "No template slots"


def test_prompt_pack_unresolved_placeholder_fails(tmp_path) -> None:
    _write_prompt(tmp_path / "prompts" / "example.md", body="Hello {{ name }}\n", required_variables="")

    with pytest.raises(PromptPackError, match="unresolved placeholder"):
        render_prompt("example", {}, prompt_root=tmp_path)


def test_prompt_pack_hash_is_stable_for_same_input(tmp_path) -> None:
    _write_prompt(tmp_path / "prompts" / "example.md")

    first = render_prompt("example", {"name": "MetaLoop"}, prompt_root=tmp_path)
    second = render_prompt("example", {"name": "MetaLoop"}, prompt_root=tmp_path)

    assert first.sha256 == second.sha256


def test_existing_prompt_files_metadata_valid_and_renderable() -> None:
    root = Path(__file__).resolve().parents[1]
    prompt_inputs = {
        "co_design/brainstorm": {
            "mission_spec": "{}",
            "co_design_draft": "{}",
            "mission_spec_review": "{}",
        },
        "co_design/discovery": {
            "patch_mode": "safe",
            "patch_mode_instruction": "SAFE MODE: draft_patch may include only audience, background, constraints, out_of_scope.",
            "co_design_draft": "{}",
        },
        "run/soft_reviewer": {
            "mission_spec": "{}",
            "goal_contract": "{}",
            "verification_result": "{}",
            "soft_review_schema": "{}",
        },
        "run/repair": {
            "mission_spec": "{}",
            "verification_result": "{}",
            "repair_attempt_index": "1",
            "failed_fix_summary": "no prior failed repair",
        },
        "run/redesign": {
            "route_role": "architect",
            "reviewer_route": "ask_architect_to_rethink",
            "mission_spec": "{}",
            "mission_capsule": "{}",
            "verification_result": "{}",
            "soft_review_decision": "{}",
        },
    }

    for prompt_id, variables in prompt_inputs.items():
        rendered = render_prompt(prompt_id, variables, prompt_root=root)
        assert rendered.metadata["id"]
        assert rendered.metadata["stage"]
        assert rendered.metadata["required_variables"]
        assert "{{" not in rendered.rendered_text
