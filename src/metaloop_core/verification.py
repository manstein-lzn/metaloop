from __future__ import annotations

from typing import Any


def verify_attempt(store: Any, attempt_id: str) -> dict[str, Any]:
    """Run the locked VerificationSpec through the canonical durable store."""

    return store.evaluate_verify(attempt_id)
