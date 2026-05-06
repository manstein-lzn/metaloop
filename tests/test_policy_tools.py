from pathlib import Path

import pytest

from metaloop.policy import PolicyEngine
from metaloop.schemas import AcceptanceCriteria, BudgetUsage, MissionSpec, PolicyScope, RiskLevel
from metaloop.tools import make_default_registry


def test_policy_blocks_workspace_escape(tmp_path) -> None:
    mission = MissionSpec(
        intent="Write something",
        acceptance_criteria=[AcceptanceCriteria(description="File exists")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    decision = PolicyEngine().check_workspace_path(mission, tmp_path.parent / "escape.txt")

    assert decision.allowed is False
    assert "outside" in decision.reason


def test_policy_blocks_denied_tool(tmp_path) -> None:
    mission = MissionSpec(
        intent="Echo something",
        acceptance_criteria=[AcceptanceCriteria(description="Text exists")],
        policy=PolicyScope(workspace_root=str(tmp_path), denied_tools=["artifact.echo"]),
    )

    with pytest.raises(PermissionError):
        make_default_registry().call(mission, "artifact.echo", {"content": "hello"})


def test_workspace_write_tool_writes_inside_workspace(tmp_path) -> None:
    mission = MissionSpec(
        intent="Write something",
        acceptance_criteria=[AcceptanceCriteria(description="File exists")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    artifact = make_default_registry().call(
        mission,
        "workspace.write_text",
        {"path": "out/result.txt", "content": "hello"},
    )

    assert artifact.kind == "file"
    assert Path(artifact.uri or "").read_text(encoding="utf-8") == "hello"


def test_high_risk_tool_requires_auth(tmp_path) -> None:
    mission = MissionSpec(
        intent="Echo something",
        acceptance_criteria=[AcceptanceCriteria(description="Text exists")],
        policy=PolicyScope(workspace_root=str(tmp_path)),
    )

    decision = PolicyEngine().check_tool(mission, "dangerous.tool", RiskLevel.HIGH)

    assert decision.allowed is False
    assert decision.requires_auth is True


def test_policy_allows_unlimited_default_token_budget() -> None:
    mission = MissionSpec(
        intent="Write something",
        acceptance_criteria=[AcceptanceCriteria(description="File exists")],
    )

    decision = PolicyEngine().check_budget(mission, BudgetUsage(tokens=999_999_999))

    assert decision.allowed is True


def test_policy_blocks_explicit_token_budget() -> None:
    mission = MissionSpec(
        intent="Write something",
        acceptance_criteria=[AcceptanceCriteria(description="File exists")],
    )
    mission.budget.max_tokens = 10

    decision = PolicyEngine().check_budget(mission, BudgetUsage(tokens=11))

    assert decision.allowed is False
    assert decision.reason == "token budget exceeded"


def test_policy_allows_unlimited_default_tool_call_budget() -> None:
    mission = MissionSpec(
        intent="Write something",
        acceptance_criteria=[AcceptanceCriteria(description="File exists")],
    )

    decision = PolicyEngine().check_budget(mission, BudgetUsage(tool_calls=999_999))

    assert decision.allowed is True


def test_policy_blocks_explicit_tool_call_budget() -> None:
    mission = MissionSpec(
        intent="Write something",
        acceptance_criteria=[AcceptanceCriteria(description="File exists")],
    )
    mission.budget.max_tool_calls = 2

    decision = PolicyEngine().check_budget(mission, BudgetUsage(tool_calls=3))

    assert decision.allowed is False
    assert decision.reason == "tool call budget exceeded"
