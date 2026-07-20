from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def new_id(prefix: str) -> str:
    """Return a short stable-looking id for local protocol artifacts."""

    normalized = prefix.strip() or "id"
    return f"{normalized}_{uuid4().hex[:12]}"


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""

    return datetime.now(UTC).isoformat()
