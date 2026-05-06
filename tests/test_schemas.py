import pytest
from pydantic import ValidationError

from metaloop.schemas import AcceptanceCriteria, MissionSpec


def test_mission_spec_requires_acceptance_criteria() -> None:
    with pytest.raises(ValidationError):
        MissionSpec(intent="Do something", acceptance_criteria=[])


def test_mission_spec_defaults_to_unlocked() -> None:
    mission = MissionSpec(
        intent="Create artifact",
        acceptance_criteria=[AcceptanceCriteria(description="Artifact exists")],
    )

    assert mission.locked is False
    assert mission.policy.workspace_root == "."
    assert mission.budget.max_tokens is None
    assert mission.budget.max_tool_calls is None
    assert mission.budget.max_step_retries == 3
