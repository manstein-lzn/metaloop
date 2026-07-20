from __future__ import annotations


def classify_dissatisfaction(decision: str) -> str:
    """Validate an explicit repair/redesign decision without inferring semantics."""

    normalized = decision.strip().lower()
    if normalized not in {"repair", "redesign", "resume", "complete"}:
        raise ValueError("decision must be explicit: repair, redesign, resume, or complete")
    return normalized
