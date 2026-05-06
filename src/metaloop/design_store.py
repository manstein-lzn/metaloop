from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from metaloop.co_design import CoDesignDraft, CoDesignRound
from metaloop.schemas import utc_now


class CoDesignCheckpoint(BaseModel):
    draft: CoDesignDraft
    rounds: list[CoDesignRound] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


class CoDesignCheckpointStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> CoDesignCheckpoint | None:
        if not self.path.exists():
            return None
        return CoDesignCheckpoint.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, draft: CoDesignDraft, rounds: list[CoDesignRound]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = CoDesignCheckpoint(draft=draft, rounds=rounds, updated_at=utc_now())
        self.path.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
