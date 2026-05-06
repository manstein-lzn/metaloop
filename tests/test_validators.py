from metaloop.kernel import MetaLoopKernel
from metaloop.schemas import AcceptanceCriteria, Budget, MissionSpec, PolicyScope, Route, RunStatus
from metaloop.validators import ArtifactValidator


def test_file_exists_validator_passes_inside_workspace(tmp_path) -> None:
    (tmp_path / "done.txt").write_text("ok", encoding="utf-8")
    mission = MissionSpec(
        intent="Validate file",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="done exists",
                validation_type="file_exists",
                validation_target="done.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is True


def test_kernel_does_not_complete_when_required_validation_fails(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create a dummy artifact",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="missing file exists",
                validation_type="file_exists",
                validation_target="missing.txt",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    state = MetaLoopKernel().run(mission)

    assert state.status == RunStatus.FAILED
    assert any(event.event_type == "artifact_validated" for event in state.events)


def test_kernel_stops_validation_retries_at_step_retry_budget(tmp_path) -> None:
    mission = MissionSpec(
        intent="Create a dummy artifact",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="missing file exists",
                validation_type="file_exists",
                validation_target="missing.txt",
            )
        ],
        budget=Budget(max_step_retries=2),
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    state = MetaLoopKernel().run(mission)

    assert state.status == RunStatus.FAILED
    assert state.budget_usage.step_retries
    assert max(state.budget_usage.step_retries.values()) == 2
    assert state.review_results[-1].route == Route.FAIL
    assert "Retry budget exhausted" in state.review_results[-1].notes


def test_file_contains_validator_accepts_json_target(tmp_path) -> None:
    (tmp_path / "hello.txt").write_text("hello from autonomous co-design\n", encoding="utf-8")
    mission = MissionSpec(
        intent="Validate file content",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello content exists",
                validation_type="file_contains",
                validation_target='{"path":"hello.txt","contains":"autonomous co-design"}',
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is True


def test_file_contains_validator_accepts_delimited_target(tmp_path) -> None:
    (tmp_path / "hello.txt").write_text("hello from co-design\n", encoding="utf-8")
    mission = MissionSpec(
        intent="Validate file content",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="hello content exists",
                validation_type="file_contains",
                validation_target="hello.txt::from co-design",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is True


def test_file_exists_validator_rejects_behavior_phrase_even_if_artifact_exists(tmp_path) -> None:
    (tmp_path / "tabs").mkdir()
    (tmp_path / "tabs" / "newlines").write_text("noise", encoding="utf-8")
    mission = MissionSpec(
        intent="Validate behavior",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="tabs/newlines exists",
                validation_type="file_exists",
                validation_target="tabs/newlines",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is False
    assert "invalid path validation target" in result.message


def test_file_contains_validator_rejects_behavior_phrase_path(tmp_path) -> None:
    (tmp_path / "tabs").mkdir()
    (tmp_path / "tabs" / "newlines").write_text("ok", encoding="utf-8")
    mission = MissionSpec(
        intent="Validate behavior",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="tabs/newlines contains ok",
                validation_type="file_contains",
                validation_target='{"path":"tabs/newlines","contains":"ok"}',
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is False
    assert "invalid path validation target" in result.message


def test_schema_validator_rejects_behavior_phrase_path(tmp_path) -> None:
    (tmp_path / "tabs").mkdir()
    (tmp_path / "tabs" / "newlines").write_text("{}", encoding="utf-8")
    mission = MissionSpec(
        intent="Validate schema",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="tabs/newlines parses",
                validation_type="schema",
                validation_target="tabs/newlines",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is False
    assert "invalid path validation target" in result.message


def test_file_contains_validator_blocks_workspace_escape(tmp_path) -> None:
    mission = MissionSpec(
        intent="Validate file content",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="outside file content",
                validation_type="file_contains",
                validation_target="../outside.txt::secret",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is False
    assert "invalid path validation target" in result.message


def test_command_validator_runs_in_workspace(tmp_path) -> None:
    mission = MissionSpec(
        intent="Validate command",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="pwd works",
                validation_type="command",
                validation_target="pwd",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path), allowed_tools=["validator.command"]),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is True
    assert str(tmp_path) in result.output


def test_command_validator_requires_explicit_policy_allow(tmp_path) -> None:
    mission = MissionSpec(
        intent="Validate command",
        acceptance_criteria=[
            AcceptanceCriteria(
                description="pwd works",
                validation_type="command",
                validation_target="pwd",
            )
        ],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    result = ArtifactValidator().validate(mission)[0]

    assert result.passed is False
    assert "validator.command" in result.message
