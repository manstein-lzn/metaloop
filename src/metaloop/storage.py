from __future__ import annotations

import sqlite3
import json
from pathlib import Path

from metaloop.schemas import KernelState, RunStatus, SystemEvent, utc_now


class SQLiteRunStore:
    """SQLite-backed event and checkpoint store for local MetaLoop runs."""

    def __init__(self, path: str | Path = ".metaloop/runs.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    mission_json TEXT NOT NULL,
                    final_state_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_index INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    node TEXT,
                    step_id TEXT,
                    payload_json TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_index INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_run_index ON events(run_id, event_index);
                CREATE INDEX IF NOT EXISTS idx_checkpoints_run_index ON checkpoints(run_id, event_index);
                """
            )

    def start_run(self, state: KernelState) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runs
                    (run_id, status, mission_json, final_state_json, created_at, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?)
                """,
                (
                    state.mission.run_id,
                    state.status.value,
                    state.mission.model_dump_json(),
                    now,
                    now,
                ),
            )

    def append_event(self, event: SystemEvent, event_index: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO events
                    (event_id, run_id, event_index, event_type, node, step_id, payload_json, event_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event_index,
                    event.event_type,
                    event.node,
                    event.step_id,
                    json.dumps(event.payload),
                    event.model_dump_json(),
                    event.created_at,
                ),
            )

    def save_checkpoint(self, state: KernelState) -> None:
        event_index = len(state.events)
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (run_id, event_index, state_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (state.mission.run_id, event_index, state.model_dump_json(), now),
            )
            connection.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (state.status.value, now, state.mission.run_id),
            )

    def finish_run(self, state: KernelState) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?, final_state_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (state.status.value, state.model_dump_json(), now, state.mission.run_id),
            )

    def latest_checkpoint(self, run_id: str) -> KernelState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json FROM checkpoints
                WHERE run_id = ?
                ORDER BY event_index DESC, checkpoint_id DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return KernelState.model_validate_json(row["state_json"])

    def final_state(self, run_id: str) -> KernelState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT final_state_json FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None or row["final_state_json"] is None:
            return None
        return KernelState.model_validate_json(row["final_state_json"])

    def events_for_run(self, run_id: str) -> list[SystemEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM events
                WHERE run_id = ?
                ORDER BY event_index ASC
                """,
                (run_id,),
            ).fetchall()
        return [SystemEvent.model_validate_json(row["event_json"]) for row in rows]

    def list_runs(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, status, created_at, updated_at FROM runs
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_resumable_run_id(self) -> str | None:
        terminal = (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.PROPOSED_NEXT_TASK.value,
        )
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id FROM runs
                WHERE status NOT IN (?, ?, ?)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                terminal,
            ).fetchone()
        if row is None:
            return None
        return str(row["run_id"])
