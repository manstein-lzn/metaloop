from __future__ import annotations

from metaloop_core.schemas import DECISIONS, DECISION_TYPES


def validate_decision(decision: str) -> None:
    if decision and decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")


def validate_event_type(event_type: str) -> None:
    if event_type not in DECISION_TYPES:
        raise ValueError(f"event type must be one of {sorted(DECISION_TYPES)}")
