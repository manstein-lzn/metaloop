from metaloop.mission_loader import build_mission_from_cli, load_mission_file


def test_load_mission_json(tmp_path) -> None:
    path = tmp_path / "mission.json"
    path.write_text(
        """
        {
          "intent": "Create artifact",
          "acceptance_criteria": [{"description": "done"}],
          "policy": {"workspace_root": "."}
        }
        """,
        encoding="utf-8",
    )

    mission = load_mission_file(path)

    assert mission.intent == "Create artifact"
    assert mission.acceptance_criteria[0].description == "done"


def test_load_simple_mission_yaml(tmp_path) -> None:
    path = tmp_path / "mission.yaml"
    path.write_text(
        """
        intent: Create a file
        deliverables:
          - hello.txt
        acceptance_criteria:
          - description: hello exists
            validation_type: file_exists
            validation_target: hello.txt
            required: true
        policy:
          workspace_root: .
          risk_level: medium
        """,
        encoding="utf-8",
    )

    mission = load_mission_file(path)

    assert mission.intent == "Create a file"
    assert mission.deliverables == ["hello.txt"]
    assert mission.acceptance_criteria[0].validation_type == "file_exists"
    assert mission.acceptance_criteria[0].required is True


def test_cli_workspace_overrides_default_mission_workspace(tmp_path) -> None:
    path = tmp_path / "mission.json"
    path.write_text(
        '{"intent":"Run","acceptance_criteria":[{"description":"done"}],"policy":{"workspace_root":"."}}',
        encoding="utf-8",
    )

    mission = build_mission_from_cli(
        intent="ignored",
        criterion="ignored",
        workspace=str(tmp_path),
        mission_file=str(path),
    )

    assert mission.policy.workspace_root == str(tmp_path)


def test_cli_mission_file_default_workspace_resolves_to_mission_directory(tmp_path) -> None:
    mission_dir = tmp_path / "mission-dir"
    mission_dir.mkdir()
    path = mission_dir / "mission.json"
    path.write_text(
        '{"intent":"Run","acceptance_criteria":[{"description":"done"}],"policy":{"workspace_root":"."}}',
        encoding="utf-8",
    )

    mission = build_mission_from_cli(
        intent="ignored",
        criterion="ignored",
        workspace=".",
        mission_file=str(path),
    )

    assert mission.policy.workspace_root == str(mission_dir)
