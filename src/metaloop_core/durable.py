from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from metaloop_core.ids import new_id, utc_now


SCHEMA_VERSION = 2
TASK_LIFECYCLES = {"open", "paused", "completed", "cancelled"}
ATTEMPT_STATUSES = {"open", "sealed", "aborted"}
EVALUATION_DECISIONS = {
    "approved",
    "rejected",
    "needs_changes",
    "review_required",
    "human_acceptance_required",
    "unsupported",
    "legacy_unbound",
}
EVENT_SCOPES = {"project", "task"}
MAX_STORED_PAYLOAD_BYTES = 1024 * 1024
MAX_RECOVERY_PAYLOAD_BYTES = 4096
MAX_RESUME_BYTES = 64 * 1024
MAX_TEXT_BYTES = 16 * 1024
SYSTEM_EVENT_TYPES = {
    "task_created",
    "task_transition",
    "dependency_added",
    "dependency_removed",
    "contract_locked",
    "attempt_started",
    "attempt_sealed",
    "attempt_aborted",
    "evaluation_recorded",
    "task_completed",
}


class DurableStateError(RuntimeError):
    pass


class NotFoundError(DurableStateError):
    pass


class ConflictError(DurableStateError):
    pass


class DuplicateAttemptError(DurableStateError):
    def __init__(self, attempt_id: str) -> None:
        self.attempt_id = attempt_id
        super().__init__(f"attempt duplicates {attempt_id}; provide retry_reason to continue intentionally")


class InvalidTransitionError(DurableStateError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_hash(value: Any) -> str:
    return "sha256:" + sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _clean_text(value: str, name: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{name} must be non-empty")
    if len(cleaned.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError(f"{name} exceeds {MAX_TEXT_BYTES} bytes")
    return cleaned


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


@dataclass(frozen=True)
class RecoveryStatus:
    status: str
    source_hash: str
    saved_source_hash: str


class DurableStore:
    """SQLite-backed MetaLoop v2 durable work graph."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.metaloop_dir = self.workspace / ".metaloop"
        self.path = self.metaloop_dir / "metaloop.db"

    def initialize(self) -> Path:
        self.metaloop_dir.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_SCHEMA)
            self._apply_schema_migrations(connection)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )
            connection.execute("UPDATE projects SET schema_version = ? WHERE schema_version != ?", (SCHEMA_VERSION, SCHEMA_VERSION))
            connection.commit()
        finally:
            connection.close()
        return self.path

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if not self.path.exists():
            self.initialize()
        else:
            self._ensure_current_schema()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        if not self.path.exists():
            self.initialize()
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        self.metaloop_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _ensure_current_schema(self) -> None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
            if int(row[0]) < SCHEMA_VERSION:
                self._apply_schema_migrations(connection)
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )
                connection.execute("UPDATE projects SET schema_version = ?", (SCHEMA_VERSION,))
                connection.commit()
        finally:
            connection.close()

    def _apply_schema_migrations(self, connection: sqlite3.Connection) -> None:
        event_foreign_keys = {str(row[3]) for row in connection.execute("PRAGMA foreign_key_list(decision_events)")}
        if "evaluation_id" not in event_foreign_keys:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.executescript(_REBUILD_DECISION_EVENTS_WITH_EVALUATION_FK)
            connection.execute("PRAGMA foreign_keys = ON")
        task_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(tasks)")}
        if "spawned_by_event_id" not in task_columns:
            connection.execute(
                "ALTER TABLE tasks ADD COLUMN spawned_by_event_id TEXT REFERENCES decision_events(event_id)"
            )

    def ensure_project(self, *, project_id: str | None = None) -> dict[str, Any]:
        with self.transaction() as connection:
            current = connection.execute("SELECT * FROM projects LIMIT 1").fetchone()
            if current is not None:
                return dict(current)
            now = utc_now()
            resolved_id = project_id or new_id("project")
            connection.execute(
                "INSERT INTO projects(project_id, workspace, schema_version, state_version, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
                (resolved_id, str(self.workspace), SCHEMA_VERSION, now, now),
            )
            return dict(connection.execute("SELECT * FROM projects WHERE project_id = ?", (resolved_id,)).fetchone())

    def project(self) -> dict[str, Any]:
        with self.read() as connection:
            row = connection.execute("SELECT * FROM projects LIMIT 1").fetchone()
            if row is None:
                raise NotFoundError("project is not initialized")
            return dict(row)

    def set_default_task(self, task_id: str) -> dict[str, Any]:
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            connection.execute(
                "UPDATE projects SET default_task_id = ?, state_version = state_version + 1, updated_at = ? WHERE project_id = ?",
                (task_id, utc_now(), task["project_id"]),
            )
            return dict(connection.execute("SELECT * FROM projects WHERE project_id = ?", (task["project_id"],)).fetchone())

    def create_task(
        self,
        *,
        title: str,
        parent_task_id: str | None = None,
        spawned_by_event_id: str | None = None,
        depends_on: list[str] | tuple[str, ...] = (),
        task_id: str | None = None,
    ) -> dict[str, Any]:
        project = self.ensure_project()
        with self.transaction() as connection:
            if parent_task_id:
                parent = self._task(connection, parent_task_id)
                if parent["project_id"] != project["project_id"]:
                    raise ValueError("parent task belongs to a different project")
            if spawned_by_event_id:
                origin = self._event(connection, spawned_by_event_id)
                if origin["project_id"] != project["project_id"]:
                    raise ValueError("spawn event belongs to a different project")
                if parent_task_id and origin["scope"] == "task" and origin["task_id"] != parent_task_id:
                    raise ValueError("task-scoped spawn event must belong to the parent Task")
            now = utc_now()
            resolved_id = task_id or new_id("task")
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id, project_id, title, parent_task_id, spawned_by_event_id, lifecycle_status,
                    state_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'open', 1, ?, ?)
                """,
                (
                    resolved_id,
                    project["project_id"],
                    _clean_text(title, "title"),
                    parent_task_id,
                    spawned_by_event_id,
                    now,
                    now,
                ),
            )
            for dependency_id in dict.fromkeys(depends_on):
                self._insert_dependency(connection, resolved_id, dependency_id)
            self._append_event(
                connection,
                project_id=project["project_id"],
                scope="task",
                task_id=resolved_id,
                event_type="task_created",
                summary=f"Created task: {_clean_text(title, 'title')}",
                payload={
                    "parent_task_id": parent_task_id,
                    "spawned_by_event_id": spawned_by_event_id,
                    "depends_on": list(dict.fromkeys(depends_on)),
                },
            )
            connection.execute(
                "UPDATE projects SET default_task_id = COALESCE(default_task_id, ?), updated_at = ? WHERE project_id = ?",
                (resolved_id, now, project["project_id"]),
            )
            return self._task(connection, resolved_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.read() as connection:
            task = self._task(connection, task_id)
            return self._task_view(connection, task)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.read() as connection:
            return [self._task_view(connection, dict(row)) for row in connection.execute("SELECT * FROM tasks ORDER BY created_at, task_id")]

    def transition_task(self, task_id: str, *, lifecycle: str, expected_version: int, reason: str = "") -> dict[str, Any]:
        if lifecycle not in TASK_LIFECYCLES:
            raise ValueError(f"unknown lifecycle: {lifecycle}")
        if lifecycle == "completed":
            raise InvalidTransitionError("completed lifecycle is set only through an accepted Evaluation chain")
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            if task["lifecycle_status"] in {"completed", "cancelled"} and lifecycle != task["lifecycle_status"]:
                raise InvalidTransitionError(f"cannot transition closed task from {task['lifecycle_status']} to {lifecycle}")
            if lifecycle == "cancelled" and task["active_attempt_id"]:
                raise InvalidTransitionError("abort the active Attempt before cancelling the Task")
            self._cas_task(connection, task_id, expected_version, {"lifecycle_status": lifecycle})
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task_id,
                event_type="task_transition",
                summary=f"Task lifecycle changed to {lifecycle}.",
                decision=lifecycle,
                payload={"reason": reason},
            )
            return self._task_view(connection, self._task(connection, task_id))

    def add_dependency(self, task_id: str, dependency_id: str, *, expected_version: int) -> dict[str, Any]:
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            if task["state_version"] != expected_version:
                raise ConflictError(f"task version conflict: expected {expected_version}, current {task['state_version']}")
            if task["lifecycle_status"] != "open" or task["active_attempt_id"]:
                raise InvalidTransitionError("dependencies can only change on an open idle Task")
            self._insert_dependency(connection, task_id, dependency_id)
            self._cas_task(connection, task_id, expected_version, {})
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task_id,
                event_type="dependency_added",
                summary=f"Task now depends on {dependency_id}.",
                payload={"depends_on_task_id": dependency_id},
            )
            return self._task_view(connection, self._task(connection, task_id))

    def remove_dependency(self, task_id: str, dependency_id: str, *, expected_version: int) -> dict[str, Any]:
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            if task["state_version"] != expected_version:
                raise ConflictError(f"task version conflict: expected {expected_version}, current {task['state_version']}")
            if task["lifecycle_status"] != "open" or task["active_attempt_id"]:
                raise InvalidTransitionError("dependencies can only change on an open idle Task")
            cursor = connection.execute(
                "DELETE FROM task_dependencies WHERE task_id = ? AND depends_on_task_id = ?",
                (task_id, dependency_id),
            )
            if cursor.rowcount != 1:
                raise NotFoundError(f"Task dependency not found: {task_id} -> {dependency_id}")
            self._cas_task(connection, task_id, expected_version, {})
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task_id,
                event_type="dependency_removed",
                summary=f"Task no longer depends on {dependency_id}.",
                payload={"depends_on_task_id": dependency_id},
            )
            return self._task_view(connection, self._task(connection, task_id))

    def lock_contract(self, task_id: str, content: dict[str, Any], *, expected_version: int) -> dict[str, Any]:
        self._validate_contract(content)
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            if task["active_attempt_id"]:
                raise InvalidTransitionError("cannot replace the Contract while an Attempt is open")
            if task["lifecycle_status"] in {"completed", "cancelled"}:
                raise InvalidTransitionError("reopen or create a new Task before locking another Contract")
            revision = int(
                connection.execute("SELECT COALESCE(MAX(revision), 0) + 1 FROM contract_revisions WHERE task_id = ?", (task_id,)).fetchone()[0]
            )
            contract_id = new_id("contract")
            normalized = json.loads(canonical_json(content))
            contract_hash = content_hash(normalized)
            connection.execute(
                """
                INSERT INTO contract_revisions(
                    contract_id, task_id, revision, parent_contract_id,
                    content_json, content_hash, locked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (contract_id, task_id, revision, task["contract_head_id"], canonical_json(normalized), contract_hash, utc_now()),
            )
            self._cas_task(
                connection,
                task_id,
                expected_version,
                {"contract_head_id": contract_id, "acceptance_head_id": None},
            )
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task_id,
                event_type="contract_locked",
                summary=f"Locked ContractRevision {revision}.",
                payload={"contract_id": contract_id, "content_hash": contract_hash, "revision": revision},
            )
            return self._contract(connection, contract_id)

    def start_attempt(
        self,
        task_id: str,
        *,
        plan: str,
        input_snapshot: dict[str, Any] | None,
        expected_version: int,
        actor: str = "codex",
        retry_of_attempt_id: str | None = None,
        retry_reason: str = "",
    ) -> dict[str, Any]:
        _ensure_payload_size(input_snapshot or {}, "Attempt input snapshot")
        if len(retry_reason.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError(f"retry_reason exceeds {MAX_TEXT_BYTES} bytes")
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            if task["lifecycle_status"] != "open":
                raise InvalidTransitionError(f"Task must be open, not {task['lifecycle_status']}")
            if task["active_attempt_id"]:
                raise InvalidTransitionError(f"Task already has open Attempt {task['active_attempt_id']}")
            if not task["contract_head_id"]:
                raise InvalidTransitionError("lock a ContractRevision before starting an Attempt")
            unresolved = self._unresolved_dependencies(connection, task_id)
            if unresolved:
                raise InvalidTransitionError("Task is blocked by dependencies: " + ", ".join(unresolved))
            contract = self._contract(connection, task["contract_head_id"])
            normalized_plan = _clean_text(plan, "plan")
            snapshot = input_snapshot or {}
            snapshot_hash = content_hash(snapshot)
            plan_hash = content_hash({"plan": normalized_plan.casefold()})
            fingerprint = content_hash(
                {"contract_hash": contract["content_hash"], "plan_hash": plan_hash, "input_hash": snapshot_hash}
            )
            previous = connection.execute(
                "SELECT attempt_id FROM attempts WHERE task_id = ? AND attempt_fingerprint = ? AND status IN ('sealed', 'aborted') ORDER BY started_at DESC LIMIT 1",
                (task_id, fingerprint),
            ).fetchone()
            if previous is not None and not retry_reason.strip():
                raise DuplicateAttemptError(str(previous["attempt_id"]))
            if retry_of_attempt_id:
                retry = self._attempt(connection, retry_of_attempt_id)
                if retry["task_id"] != task_id:
                    raise ValueError("retry_of_attempt_id belongs to a different Task")
            elif previous is not None:
                retry_of_attempt_id = str(previous["attempt_id"])
            attempt_id = new_id("attempt")
            now = utc_now()
            connection.execute(
                """
                INSERT INTO attempts(
                    attempt_id, task_id, contract_id, status, plan, plan_hash,
                    input_snapshot_json, input_hash, attempt_fingerprint,
                    retry_of_attempt_id, retry_reason, actor, started_at
                ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    task_id,
                    contract["contract_id"],
                    normalized_plan,
                    plan_hash,
                    canonical_json(snapshot),
                    snapshot_hash,
                    fingerprint,
                    retry_of_attempt_id,
                    retry_reason.strip(),
                    _clean_text(actor, "actor"),
                    now,
                ),
            )
            self._cas_task(connection, task_id, expected_version, {"active_attempt_id": attempt_id, "acceptance_head_id": None})
            self._append_attempt_record(
                connection,
                attempt_id,
                "attempt_started",
                {"plan": normalized_plan, "actor": actor, "retry_of_attempt_id": retry_of_attempt_id, "retry_reason": retry_reason},
            )
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task_id,
                attempt_id=attempt_id,
                event_type="attempt_started",
                summary=f"Started Attempt {attempt_id}.",
                payload={"fingerprint": fingerprint, "retry_of_attempt_id": retry_of_attempt_id},
            )
            return self._attempt_view(connection, self._attempt(connection, attempt_id))

    def append_attempt_record(self, attempt_id: str, *, record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_payload_size(payload, "Attempt record payload")
        with self.transaction() as connection:
            attempt = self._attempt(connection, attempt_id)
            if attempt["status"] != "open":
                raise InvalidTransitionError("records can only be appended to an open Attempt")
            return self._append_attempt_record(connection, attempt_id, _clean_text(record_type, "record_type"), payload)

    def add_evidence(
        self,
        attempt_id: str,
        *,
        path: str,
        description: str = "",
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        resolved = Path(path).expanduser()
        if not resolved.is_absolute():
            resolved = (self.workspace / resolved).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        try:
            stored_path = str(resolved.relative_to(self.workspace))
        except ValueError:
            stored_path = str(resolved)
        digest = file_hash(resolved)
        if len(description.encode("utf-8")) > 4096:
            raise ValueError("evidence description exceeds 4096 bytes")
        with self.transaction() as connection:
            attempt = self._attempt(connection, attempt_id)
            if attempt["status"] != "open":
                raise InvalidTransitionError("evidence can only be added to an open Attempt")
            evidence_id = new_id("evidence")
            connection.execute(
                "INSERT INTO evidence(evidence_id, attempt_id, path, sha256, media_type, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (evidence_id, attempt_id, stored_path, digest, media_type, description.strip(), utc_now()),
            )
            self._append_attempt_record(
                connection,
                attempt_id,
                "evidence_added",
                {"evidence_id": evidence_id, "path": stored_path, "sha256": digest, "description": description},
            )
            return dict(connection.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone())

    def seal_attempt(self, attempt_id: str, *, expected_task_version: int, outcome: str = "completed") -> dict[str, Any]:
        with self.transaction() as connection:
            attempt = self._attempt(connection, attempt_id)
            if attempt["status"] != "open":
                raise InvalidTransitionError("only an open Attempt can be sealed")
            task = self._task(connection, attempt["task_id"])
            if task["active_attempt_id"] != attempt_id:
                raise ConflictError("Task active_attempt_ref does not match the Attempt")
            self._assert_live_attempt_evidence(connection, attempt, phase="seal")
            manifest = self._build_attempt_manifest(connection, attempt, outcome=_clean_text(outcome, "outcome"))
            execution_hash = content_hash(manifest)
            sealed_at = utc_now()
            connection.execute(
                "UPDATE attempts SET status = 'sealed', sealed_at = ?, execution_hash = ?, manifest_json = ? WHERE attempt_id = ? AND status = 'open'",
                (sealed_at, execution_hash, canonical_json(manifest), attempt_id),
            )
            self._cas_task(connection, task["task_id"], expected_task_version, {"active_attempt_id": None})
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task["task_id"],
                attempt_id=attempt_id,
                event_type="attempt_sealed",
                summary=f"Sealed Attempt {attempt_id}.",
                payload={"execution_hash": execution_hash, "outcome": outcome},
            )
            return self._attempt_view(connection, self._attempt(connection, attempt_id))

    def abort_attempt(self, attempt_id: str, *, expected_task_version: int, reason: str) -> dict[str, Any]:
        with self.transaction() as connection:
            attempt = self._attempt(connection, attempt_id)
            if attempt["status"] != "open":
                raise InvalidTransitionError("only an open Attempt can be aborted")
            task = self._task(connection, attempt["task_id"])
            self._append_attempt_record(connection, attempt_id, "attempt_aborted", {"reason": _clean_text(reason, "reason")})
            connection.execute("UPDATE attempts SET status = 'aborted', sealed_at = ? WHERE attempt_id = ?", (utc_now(), attempt_id))
            self._cas_task(connection, task["task_id"], expected_task_version, {"active_attempt_id": None})
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task["task_id"],
                attempt_id=attempt_id,
                event_type="attempt_aborted",
                summary=f"Aborted Attempt {attempt_id}.",
                diagnosis=reason,
            )
            return self._attempt_view(connection, self._attempt(connection, attempt_id))

    def get_attempt(self, attempt_id: str) -> dict[str, Any]:
        with self.read() as connection:
            return self._attempt_view(connection, self._attempt(connection, attempt_id))

    def list_attempts(self, task_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.read() as connection:
            self._task(connection, task_id)
            rows = connection.execute(
                "SELECT * FROM attempts WHERE task_id = ? ORDER BY started_at DESC, attempt_id DESC LIMIT ?", (task_id, max(1, limit))
            )
            return [
                self._attempt_view(connection, dict(row), record_limit=0, include_evidence=False, compact=True)
                for row in rows
            ]

    def verify_attempt(self, attempt_id: str, *, evaluator: str = "metaloop_kernel", evaluator_version: str = "2.0") -> dict[str, Any]:
        from metaloop_core.specs import validator_mode, validator_severity
        from metaloop_core.validators import run_validator

        with self.read() as connection:
            attempt = self._attempt(connection, attempt_id)
            if attempt["status"] != "sealed" or not attempt["execution_hash"]:
                raise InvalidTransitionError("only a sealed Attempt can be evaluated")
            self._assert_attempt_content(connection, attempt, phase="verification")
            contract = self._contract(connection, attempt["contract_id"])
            contract_content = contract["content"]
            spec = contract_content.get("verification_spec") if isinstance(contract_content, dict) else None
            subject_hash = str(attempt["execution_hash"])
            task_id = str(attempt["task_id"])
            contract_hash = str(contract["content_hash"])
            self._assert_live_attempt_evidence(connection, attempt, phase="verification")

        validators = spec.get("validators", []) if isinstance(spec, dict) else []
        results: list[dict[str, Any]] = []
        manual: list[dict[str, Any]] = []
        unsupported: list[dict[str, Any]] = []
        for validator in validators:
            if not isinstance(validator, dict):
                continue
            mode = validator_mode(validator)
            severity = validator_severity(validator)
            if mode == "manual":
                manual.append({"validator": validator, "severity": severity})
            elif mode == "unsupported":
                unsupported.append({"validator": validator, "severity": severity})
            else:
                result = run_validator(self.workspace, validator)
                result["severity"] = severity
                results.append(result)
        for gate in spec.get("resource_gates", []) if isinstance(spec, dict) else []:
            if isinstance(gate, dict):
                manual.append({"validator": {**gate, "type": "resource_gate"}, "severity": validator_severity(gate)})
        failures = [item for item in results if item.get("severity") == "blocking" and not item.get("passed")]
        blocking_unsupported = [item for item in unsupported if item.get("severity") == "blocking"]
        human = [
            item
            for item in manual
            if item.get("severity") == "blocking" and _manual_authority(item.get("validator", {})) == "user"
        ]
        reviewer = [
            item
            for item in manual
            if item.get("severity") == "blocking" and _manual_authority(item.get("validator", {})) != "user"
        ]
        if failures:
            decision = "rejected"
        elif blocking_unsupported:
            decision = "unsupported"
        elif human:
            decision = "human_acceptance_required"
        elif reviewer:
            decision = "review_required"
        elif not results:
            decision = "unsupported"
        else:
            decision = "approved"
        payload = {
            "verification_spec_hash": content_hash(spec or {}),
            "validator_results": results,
            "manual_validators": manual,
            "unsupported_validators": unsupported,
            "artifact_bindings": self._artifact_bindings(validators),
            "required_authorities": sorted(
                {*("reviewer" for _ in reviewer), *("user" for _ in human)}
            ),
        }
        with self.transaction() as connection:
            current_attempt = self._attempt(connection, attempt_id)
            current_contract = self._contract(connection, current_attempt["contract_id"])
            if current_attempt["status"] != "sealed" or current_attempt["execution_hash"] != subject_hash:
                raise ConflictError("Attempt changed while validators were running")
            if current_contract["content_hash"] != contract_hash:
                raise ConflictError("ContractRevision changed while validators were running")
            self._assert_attempt_content(connection, current_attempt, phase="verification")
            self._assert_live_attempt_evidence(connection, current_attempt, phase="verification")
            return self._insert_evaluation(
                connection,
                task_id=task_id,
                subject_type="attempt",
                subject_id=attempt_id,
                subject_hash=subject_hash,
                kind="verification",
                authority="kernel",
                evaluator=evaluator,
                evaluator_version=evaluator_version,
                decision=decision,
                payload=payload,
            )

    def review_evaluation(
        self,
        evaluation_id: str,
        *,
        decision: str,
        reviewer: str,
        reviewer_role: str = "reviewer",
        authority: str = "reviewer",
        notes: str = "",
    ) -> dict[str, Any]:
        if decision not in {"approved", "rejected", "needs_changes"}:
            raise ValueError("review decision must be approved, rejected, or needs_changes")
        if reviewer_role.casefold() in {"worker", "worker-main", "primary_worker"}:
            raise ValueError("reviewer_role must be independent from the worker role")
        if authority not in {"reviewer", "user"}:
            raise ValueError("authority must be reviewer or user")
        with self.transaction() as connection:
            subject = self._evaluation(connection, evaluation_id)
            attempt = self._root_attempt_for_evaluation(connection, subject)
            if authority != "user" and reviewer.strip().casefold() == str(attempt.get("actor") or "").casefold():
                raise ValueError("reviewer must be independent from the Attempt actor")
            return self._insert_evaluation(
                connection,
                task_id=subject["task_id"],
                subject_type="evaluation",
                subject_id=evaluation_id,
                subject_hash=subject["content_hash"],
                kind="review" if authority == "reviewer" else "human_acceptance",
                authority=authority,
                evaluator=_clean_text(reviewer, "reviewer"),
                evaluator_version="1.0",
                decision=decision,
                payload={"reviewer_role": reviewer_role, "notes": notes},
            )

    def accept_task(self, task_id: str, *, terminal_evaluation_id: str, expected_version: int) -> dict[str, Any]:
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            if task["state_version"] != expected_version:
                raise ConflictError(f"task version conflict: expected {expected_version}, current {task['state_version']}")
            if task["lifecycle_status"] == "cancelled":
                raise InvalidTransitionError("cancelled Task cannot be accepted")
            if task["lifecycle_status"] == "completed":
                if task["acceptance_head_id"] == terminal_evaluation_id:
                    return self._task_view(connection, task)
                raise InvalidTransitionError("completed Task already has a different acceptance head")
            if task["active_attempt_id"]:
                raise InvalidTransitionError("cannot complete a Task while an Attempt is open")
            unresolved = self._unresolved_dependencies(connection, task_id)
            if unresolved:
                raise InvalidTransitionError("cannot complete a Task with unresolved dependencies: " + ", ".join(unresolved))
            chain, attempt = self._evaluation_chain(connection, terminal_evaluation_id)
            if attempt["task_id"] != task_id:
                raise ValueError("Evaluation chain belongs to a different Task")
            if attempt["contract_id"] != task["contract_head_id"]:
                raise InvalidTransitionError("Evaluation chain does not use the current ContractRevision")
            self._validate_acceptance_chain(chain)
            self._assert_live_attempt_evidence(connection, attempt, phase="acceptance")
            self._cas_task(
                connection,
                task_id,
                expected_version,
                {"acceptance_head_id": terminal_evaluation_id, "lifecycle_status": "completed"},
            )
            self._append_event(
                connection,
                project_id=task["project_id"],
                scope="task",
                task_id=task_id,
                attempt_id=attempt["attempt_id"],
                evaluation_id=terminal_evaluation_id,
                event_type="task_completed",
                summary=f"Completed Task through Evaluation {terminal_evaluation_id}.",
                decision="complete",
            )
            return self._task_view(connection, self._task(connection, task_id))

    def get_evaluation(self, evaluation_id: str) -> dict[str, Any]:
        with self.read() as connection:
            return self._evaluation_view(connection, self._evaluation(connection, evaluation_id))

    def list_evaluations(self, task_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
        with self.read() as connection:
            self._task(connection, task_id)
            rows = connection.execute(
                "SELECT * FROM evaluations WHERE task_id = ? ORDER BY evaluation_seq DESC LIMIT ?", (task_id, max(1, limit))
            )
            return [self._evaluation_view(connection, dict(row)) for row in rows]

    def record_decision(
        self,
        *,
        scope: str,
        event_type: str,
        summary: str,
        task_id: str | None = None,
        attempt_id: str | None = None,
        evaluation_id: str | None = None,
        diagnosis: str = "",
        decision: str = "",
        next_plan: str = "",
        supersedes_event_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _ensure_payload_size(payload or {}, "DecisionEvent payload")
        _clean_text(event_type, "DecisionEvent type")
        _clean_text(summary, "DecisionEvent summary")
        for value, name in [
            (diagnosis, "DecisionEvent diagnosis"),
            (decision, "DecisionEvent decision"),
            (next_plan, "DecisionEvent next_plan"),
        ]:
            if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
                raise ValueError(f"{name} exceeds {MAX_TEXT_BYTES} bytes")
        project = self.ensure_project()
        if scope not in EVENT_SCOPES:
            raise ValueError(f"scope must be one of {sorted(EVENT_SCOPES)}")
        if scope == "task" and not task_id:
            raise ValueError("task-scoped DecisionEvent requires task_id")
        if scope == "project" and task_id:
            raise ValueError("project-scoped DecisionEvent must not set task_id")
        with self.transaction() as connection:
            if task_id:
                task = self._task(connection, task_id)
                if task["project_id"] != project["project_id"]:
                    raise ValueError("Task belongs to a different project")
            if scope == "project" and (attempt_id or evaluation_id):
                raise ValueError("project-scoped DecisionEvent cannot bind Task Attempt/Evaluation subjects")
            attempt = self._attempt(connection, attempt_id) if attempt_id else None
            evaluation = self._evaluation(connection, evaluation_id) if evaluation_id else None
            if attempt and attempt["task_id"] != task_id:
                raise ValueError("DecisionEvent Attempt belongs to a different Task")
            if evaluation and evaluation["task_id"] != task_id:
                raise ValueError("DecisionEvent Evaluation belongs to a different Task")
            if attempt and evaluation:
                root_attempt = self._root_attempt_for_evaluation(connection, evaluation)
                if root_attempt["attempt_id"] != attempt_id:
                    raise ValueError("DecisionEvent Attempt and Evaluation do not belong to the same chain")
            if supersedes_event_id:
                previous = connection.execute("SELECT scope, task_id FROM decision_events WHERE event_id = ?", (supersedes_event_id,)).fetchone()
                if previous is None:
                    raise NotFoundError(f"DecisionEvent not found: {supersedes_event_id}")
                if previous["scope"] != scope or previous["task_id"] != task_id:
                    raise ValueError("superseded event must have the same scope")
            return self._append_event(
                connection,
                project_id=project["project_id"],
                scope=scope,
                task_id=task_id,
                attempt_id=attempt_id,
                evaluation_id=evaluation_id,
                event_type=_clean_text(event_type, "event_type"),
                summary=_clean_text(summary, "summary"),
                diagnosis=diagnosis,
                decision=decision,
                next_plan=next_plan,
                supersedes_event_id=supersedes_event_id,
                payload=payload or {},
            )

    def get_event(self, event_id: str) -> dict[str, Any]:
        with self.read() as connection:
            return self._event_view(self._event(connection, event_id))

    def list_events(
        self,
        *,
        task_id: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if scope is not None and scope not in EVENT_SCOPES:
            raise ValueError(f"scope must be one of {sorted(EVENT_SCOPES)}")
        with self.read() as connection:
            clauses: list[str] = []
            values: list[Any] = []
            if task_id:
                task = self._task(connection, task_id)
                clauses.append("project_id = ?")
                values.append(task["project_id"])
                clauses.append("(task_id = ? OR scope = 'project')")
                values.append(task_id)
            if scope:
                clauses.append("scope = ?")
                values.append(scope)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            values.append(min(max(1, limit), 10000))
            rows = connection.execute(
                f"SELECT * FROM decision_events{where} ORDER BY event_seq DESC LIMIT ?",
                values,
            )
            return [self._event_view(dict(row)) for row in rows]

    def write_recovery(self, task_id: str, *, resume_markdown: str = "") -> dict[str, Any]:
        if len(resume_markdown.encode("utf-8")) > MAX_RESUME_BYTES:
            raise ValueError(f"resume Markdown exceeds {MAX_RESUME_BYTES} bytes")
        with self.transaction() as connection:
            task = self._task(connection, task_id)
            source = self._recovery_source(connection, task)
            source_digest = content_hash(source)
            resume = resume_markdown.strip() or self._default_resume(connection, task, source)
            if len(resume.encode("utf-8")) > MAX_RESUME_BYTES:
                raise ValueError(f"resume Markdown exceeds {MAX_RESUME_BYTES} bytes")
            connection.execute(
                """
                INSERT INTO recovery_views(task_id, source_json, source_hash, resume_markdown, generated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    source_json = excluded.source_json,
                    source_hash = excluded.source_hash,
                    resume_markdown = excluded.resume_markdown,
                    generated_at = excluded.generated_at
                """,
                (task_id, canonical_json(source), source_digest, resume.rstrip() + "\n", utc_now()),
            )
            return self._recovery_bundle(connection, task)

    def recovery(self, task_id: str) -> dict[str, Any]:
        with self.read() as connection:
            return self._recovery_bundle(connection, self._task(connection, task_id))

    def assign_thread(self, thread_id: str, task_id: str, *, push_focus: bool = True) -> dict[str, Any]:
        project = self.ensure_project()
        with self.transaction() as connection:
            self._task(connection, task_id)
            current = connection.execute("SELECT * FROM thread_assignments WHERE thread_id = ?", (thread_id,)).fetchone()
            stack = _json_load(current["focus_stack_json"], []) if current is not None else []
            if push_focus and current is not None and current["task_id"] and current["task_id"] != task_id:
                stack.append(current["task_id"])
            connection.execute(
                """
                INSERT INTO thread_assignments(thread_id, project_id, task_id, focus_stack_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    task_id = excluded.task_id,
                    focus_stack_json = excluded.focus_stack_json,
                    updated_at = excluded.updated_at
                """,
                (thread_id, project["project_id"], task_id, canonical_json(stack), utc_now()),
            )
            return self._thread_assignment_view(
                dict(connection.execute("SELECT * FROM thread_assignments WHERE thread_id = ?", (thread_id,)).fetchone())
            )

    def list_thread_assignments(self) -> list[dict[str, Any]]:
        with self.read() as connection:
            rows = connection.execute("SELECT * FROM thread_assignments ORDER BY updated_at DESC, thread_id")
            return [self._thread_assignment_view(dict(row)) for row in rows]

    def get_thread_assignment(self, thread_id: str) -> dict[str, Any]:
        with self.read() as connection:
            row = connection.execute("SELECT * FROM thread_assignments WHERE thread_id = ?", (thread_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"thread assignment not found: {thread_id}")
            return self._thread_assignment_view(dict(row))

    def return_thread(self, thread_id: str) -> dict[str, Any]:
        with self.transaction() as connection:
            current = connection.execute("SELECT * FROM thread_assignments WHERE thread_id = ?", (thread_id,)).fetchone()
            if current is None:
                raise NotFoundError(f"thread assignment not found: {thread_id}")
            stack = _json_load(current["focus_stack_json"], [])
            if not stack:
                raise InvalidTransitionError("thread focus stack is empty")
            task_id = stack.pop()
            self._task(connection, task_id)
            connection.execute(
                "UPDATE thread_assignments SET task_id = ?, focus_stack_json = ?, updated_at = ? WHERE thread_id = ?",
                (task_id, canonical_json(stack), utc_now(), thread_id),
            )
            return self._thread_assignment_view(
                dict(connection.execute("SELECT * FROM thread_assignments WHERE thread_id = ?", (thread_id,)).fetchone())
            )

    def migrate_legacy(self, *, title: str = "Imported legacy MetaLoop mission") -> dict[str, Any]:
        capsule = _read_json(self.metaloop_dir / "mission_capsule.json") or {}
        execution = _read_json(self.metaloop_dir / "execution_report.json")
        verification = _read_json(self.metaloop_dir / "verification_result.json")
        review = _read_json(self.metaloop_dir / "review_result.json")
        legacy_bound, validation = self._validate_legacy_binding(capsule, execution, verification)
        project = self.ensure_project()
        contract_content = {
            "goal": capsule.get("intent") or title,
            "context": capsule.get("context", []),
            "rationale": capsule.get("design_rationale", []),
            "constraints": capsule.get("constraints", []),
            "non_goals": capsule.get("non_goals", []),
            "acceptance_criteria": capsule.get("acceptance_criteria", []),
            "verification_spec": capsule.get("verification_spec", {"validators": []}),
            "legacy": {"capsule_id": capsule.get("capsule_id"), "revision": capsule.get("revision")},
        }
        self._validate_contract(contract_content)
        with self.transaction() as connection:
            if connection.execute("SELECT 1 FROM tasks LIMIT 1").fetchone() is not None:
                raise InvalidTransitionError("legacy migration requires a v2 project with no Tasks")
            now = utc_now()
            task_id = new_id("task")
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id, project_id, title, parent_task_id, spawned_by_event_id,
                    lifecycle_status, state_version, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, 'open', 1, ?, ?)
                """,
                (task_id, project["project_id"], _clean_text(title, "title"), now, now),
            )
            self._append_event(
                connection,
                project_id=project["project_id"],
                scope="task",
                task_id=task_id,
                event_type="task_created",
                summary=f"Created task: {_clean_text(title, 'title')}",
                payload={"legacy_migration": True},
            )
            contract_id = new_id("contract")
            normalized_contract = json.loads(canonical_json(contract_content))
            contract_hash = content_hash(normalized_contract)
            connection.execute(
                """
                INSERT INTO contract_revisions(
                    contract_id, task_id, revision, parent_contract_id,
                    content_json, content_hash, locked_at
                ) VALUES (?, ?, 1, NULL, ?, ?, ?)
                """,
                (contract_id, task_id, canonical_json(normalized_contract), contract_hash, utc_now()),
            )
            self._cas_task(connection, task_id, 1, {"contract_head_id": contract_id})
            self._append_event(
                connection,
                project_id=project["project_id"],
                scope="task",
                task_id=task_id,
                event_type="contract_locked",
                summary="Locked imported legacy ContractRevision 1.",
                payload={"contract_id": contract_id, "content_hash": contract_hash, "revision": 1},
            )
            connection.execute(
                "UPDATE projects SET default_task_id = ?, updated_at = ? WHERE project_id = ?",
                (task_id, utc_now(), project["project_id"]),
            )
            imported: dict[str, Any] = {
                "project_id": project["project_id"],
                "task_id": task_id,
                "contract_id": contract_id,
                "legacy_bound": False,
                "legacy_validation": validation,
            }
            if execution:
                plan = "Import the legacy ExecutionReport as historical evidence."
                input_snapshot = {"legacy_execution_hash": content_hash(execution)}
                input_hash = content_hash(input_snapshot)
                plan_hash = content_hash({"plan": plan.casefold()})
                fingerprint = content_hash(
                    {"contract_hash": contract_hash, "plan_hash": plan_hash, "input_hash": input_hash}
                )
                attempt_id = new_id("attempt")
                started_at = utc_now()
                connection.execute(
                    """
                    INSERT INTO attempts(
                        attempt_id, task_id, contract_id, status, plan, plan_hash,
                        input_snapshot_json, input_hash, attempt_fingerprint,
                        retry_of_attempt_id, retry_reason, actor, started_at
                    ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, NULL, '', 'legacy_import', ?)
                    """,
                    (
                        attempt_id,
                        task_id,
                        contract_id,
                        plan,
                        plan_hash,
                        canonical_json(input_snapshot),
                        input_hash,
                        fingerprint,
                        started_at,
                    ),
                )
                self._cas_task(connection, task_id, 2, {"active_attempt_id": attempt_id})
                self._append_attempt_record(
                    connection,
                    attempt_id,
                    "attempt_started",
                    {"plan": plan, "actor": "legacy_import", "retry_of_attempt_id": None, "retry_reason": ""},
                )
                self._append_attempt_record(connection, attempt_id, "legacy_execution", execution)
                self._append_event(
                    connection,
                    project_id=project["project_id"],
                    scope="task",
                    task_id=task_id,
                    attempt_id=attempt_id,
                    event_type="attempt_started",
                    summary=f"Started imported legacy Attempt {attempt_id}.",
                    payload={"fingerprint": fingerprint},
                )
                attempt = self._attempt(connection, attempt_id)
                manifest = self._build_attempt_manifest(
                    connection,
                    attempt,
                    outcome=str(execution.get("status") or "imported"),
                )
                execution_hash = content_hash(manifest)
                connection.execute(
                    "UPDATE attempts SET status = 'sealed', sealed_at = ?, execution_hash = ?, manifest_json = ? WHERE attempt_id = ?",
                    (utc_now(), execution_hash, canonical_json(manifest), attempt_id),
                )
                self._cas_task(connection, task_id, 3, {"active_attempt_id": None})
                self._append_event(
                    connection,
                    project_id=project["project_id"],
                    scope="task",
                    task_id=task_id,
                    attempt_id=attempt_id,
                    event_type="attempt_sealed",
                    summary=f"Sealed imported legacy Attempt {attempt_id}.",
                    payload={"execution_hash": execution_hash, "outcome": manifest["outcome"]},
                )
                imported["attempt_id"] = attempt_id
                if verification:
                    evaluation = self._insert_evaluation(
                        connection,
                        task_id=task_id,
                        subject_type="attempt",
                        subject_id=attempt_id,
                        subject_hash=execution_hash,
                        kind="legacy_verification",
                        authority="legacy",
                        evaluator="legacy_import",
                        evaluator_version="1.0",
                        decision="approved" if legacy_bound else "legacy_unbound",
                        payload={
                            "legacy_verification": verification,
                            "legacy_review": review,
                            "bound_to_execution": legacy_bound,
                            "validation": validation,
                            "required_authorities": [],
                        },
                    )
                    imported["evaluation_id"] = evaluation["evaluation_id"]
                    imported["legacy_bound"] = legacy_bound
            task = self._task(connection, task_id)
            source = self._recovery_source(connection, task)
            source_hash = content_hash(source)
            connection.execute(
                "INSERT INTO recovery_views(task_id, source_json, source_hash, resume_markdown, generated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    task_id,
                    canonical_json(source),
                    source_hash,
                    self._default_resume(connection, task, source).rstrip() + "\n",
                    utc_now(),
                ),
            )
            return imported

    def _validate_legacy_binding(
        self,
        capsule: dict[str, Any],
        execution: dict[str, Any] | None,
        verification: dict[str, Any] | None,
    ) -> tuple[bool, dict[str, Any]]:
        from metaloop_core.capsule import validate_capsule
        from metaloop_core.execution import validate_execution_report
        from metaloop_core.verification import verify_workspace

        errors = validate_capsule(capsule)
        if execution is None:
            errors.append("legacy ExecutionReport is missing")
        else:
            errors.extend(validate_execution_report(execution, capsule))
            if execution.get("status") != "completed":
                errors.append("legacy ExecutionReport is not completed")
        if verification is None:
            errors.append("legacy VerificationResult is missing")
        recomputed: dict[str, Any] | None = None
        if not errors:
            recomputed = verify_workspace(self.workspace, write=False, update_status=False)
            bindings = [
                "status",
                "capsule_id",
                "capsule_revision",
                "execution_id",
                "execution_hash",
                "verification_spec_hash",
            ]
            for key in bindings:
                if verification.get(key) != recomputed.get(key):
                    errors.append(f"legacy VerificationResult {key} does not match fresh verification")
            if recomputed.get("status") != "completed_verified":
                errors.append(f"fresh legacy verification is {recomputed.get('status') or 'invalid'}")
        return not errors, {
            "recomputed_status": recomputed.get("status") if recomputed else None,
            "errors": errors,
        }

    def export_project(self) -> Path:
        project = self.project()
        target = self.metaloop_dir / "v2"
        _atomic_write_json(target / "project.json", project)
        _atomic_write_json(target / "events.json", list(reversed(self.list_events(limit=10000))))
        for task in self.list_tasks():
            task_dir = target / "tasks" / task["task_id"]
            recovery = self.recovery(task["task_id"])
            _atomic_write_json(task_dir / "task.json", task)
            if task.get("contract"):
                _atomic_write_json(task_dir / "contract.json", task["contract"])
            _atomic_write_json(task_dir / "attempts.json", self.list_attempts(task["task_id"], limit=1000))
            _atomic_write_json(task_dir / "evaluations.json", self.list_evaluations(task["task_id"], limit=1000))
            _atomic_write_json(
                task_dir / "events.json",
                list(reversed(self.list_events(task_id=task["task_id"], scope="task", limit=10000))),
            )
            _atomic_write_json(task_dir / "recovery_head.json", {key: value for key, value in recovery.items() if key != "resume_markdown"})
            _atomic_write_text(task_dir / "resume.md", recovery.get("resume_markdown") or "# Resume\n")
        return target

    def observation(self) -> dict[str, Any]:
        project = self.project()
        tasks = self.list_tasks()
        selected = next((item for item in tasks if item["task_id"] == project.get("default_task_id")), tasks[0] if tasks else None)
        if selected is None:
            return {"schema": "metaloop.v2_observation", "project": project, "task_count": 0, "selected_task": None, "recovery_status": "incomplete"}
        recovery = self.recovery(selected["task_id"])
        latest_evaluation = recovery["latest_evaluations"][0] if recovery["latest_evaluations"] else None
        with self.read() as connection:
            latest_event_row = connection.execute(
                """
                SELECT * FROM decision_events
                WHERE task_id = ? OR (project_id = ? AND scope = 'project')
                ORDER BY event_seq DESC LIMIT 1
                """,
                (selected["task_id"], project["project_id"]),
            ).fetchone()
            latest_plan_row = connection.execute(
                "SELECT next_plan FROM decision_events WHERE task_id = ? AND next_plan != '' ORDER BY event_seq DESC LIMIT 1",
                (selected["task_id"],),
            ).fetchone()
        latest_event = dict(latest_event_row) if latest_event_row is not None else None
        if latest_event is not None:
            latest_event["payload"] = _json_load(latest_event.pop("payload_json"), {})
        current_plan = ""
        if recovery["active_attempt"]:
            current_plan = str(recovery["active_attempt"].get("plan") or "")
        elif latest_plan_row is not None:
            current_plan = str(latest_plan_row["next_plan"] or "")
        goal = ""
        contract = selected.get("contract")
        if isinstance(contract, dict) and isinstance(contract.get("content"), dict):
            goal = str(contract["content"].get("goal") or contract["content"].get("intent") or "")
        return {
            "schema": "metaloop.v2_observation",
            "project": project,
            "task_count": len(tasks),
            "selected_task": selected,
            "status": selected["readiness"],
            "goal": goal,
            "current_plan": current_plan,
            "latest_evaluation": latest_evaluation,
            "latest_event": latest_event,
            "recovery_status": recovery["status"],
            "integrity": self.integrity_check(),
        }

    def integrity_check(self) -> dict[str, Any]:
        with self.read() as connection:
            sqlite_result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            errors: list[str] = []
            workspace_errors: list[str] = []
            foreign_key_rows = list(connection.execute("PRAGMA foreign_key_check"))
            for row in foreign_key_rows:
                errors.append(f"foreign key violation: {tuple(row)}")
            project = connection.execute("SELECT * FROM projects LIMIT 1").fetchone()
            if project is not None and int(project["schema_version"]) != SCHEMA_VERSION:
                errors.append(
                    f"project schema version mismatch: {project['schema_version']} != {SCHEMA_VERSION}"
                )
            for contract_row in connection.execute("SELECT * FROM contract_revisions"):
                contract = self._contract(connection, str(contract_row["contract_id"]))
                if content_hash(contract["content"]) != contract["content_hash"]:
                    errors.append(f"contract hash mismatch: {contract['contract_id']}")
                if contract["parent_contract_id"]:
                    parent = self._contract(connection, contract["parent_contract_id"])
                    if parent["task_id"] != contract["task_id"] or int(parent["revision"]) >= int(contract["revision"]):
                        errors.append(f"contract parent mismatch: {contract['contract_id']}")
            for attempt_row in connection.execute("SELECT * FROM attempts"):
                attempt = dict(attempt_row)
                task = self._task(connection, attempt["task_id"])
                contract = self._contract(connection, attempt["contract_id"])
                if contract["task_id"] != task["task_id"]:
                    errors.append(f"Attempt contract belongs to another Task: {attempt['attempt_id']}")
                errors.extend(self._attempt_content_errors(connection, attempt))
            for evaluation_row in connection.execute("SELECT * FROM evaluations"):
                try:
                    self._evaluation_chain(connection, str(evaluation_row["evaluation_id"]))
                except DurableStateError as exc:
                    errors.append(str(exc))
            for event_row in connection.execute("SELECT * FROM decision_events"):
                event = dict(event_row)
                immutable = {
                    "event_id": event["event_id"],
                    "project_id": event["project_id"],
                    "scope": event["scope"],
                    "task_id": event["task_id"],
                    "attempt_id": event["attempt_id"],
                    "evaluation_id": event["evaluation_id"],
                    "type": event["type"],
                    "summary": event["summary"],
                    "diagnosis": event["diagnosis"],
                    "decision": event["decision"],
                    "next_plan": event["next_plan"],
                    "supersedes_event_id": event["supersedes_event_id"],
                    "payload": _json_load(event["payload_json"], {}),
                    "created_at": event["created_at"],
                }
                if content_hash(immutable) != event["content_hash"]:
                    errors.append(f"DecisionEvent hash mismatch: {event['event_id']}")
                if event["task_id"]:
                    event_task = self._task(connection, event["task_id"])
                    if event_task["project_id"] != event["project_id"]:
                        errors.append(f"DecisionEvent project mismatch: {event['event_id']}")
                if event["attempt_id"]:
                    event_attempt = self._attempt(connection, event["attempt_id"])
                    if event_attempt["task_id"] != event["task_id"]:
                        errors.append(f"DecisionEvent Attempt task mismatch: {event['event_id']}")
                if event["evaluation_id"]:
                    event_evaluation = self._evaluation(connection, event["evaluation_id"])
                    if event_evaluation["task_id"] != event["task_id"]:
                        errors.append(f"DecisionEvent Evaluation task mismatch: {event['event_id']}")
            for task in connection.execute("SELECT * FROM tasks"):
                task_dict = dict(task)
                if task_dict["contract_head_id"]:
                    contract = self._contract(connection, task_dict["contract_head_id"])
                    if contract["task_id"] != task_dict["task_id"]:
                        errors.append(f"contract head belongs to another Task: {task_dict['task_id']}")
                if task_dict["active_attempt_id"]:
                    attempt = self._attempt(connection, task_dict["active_attempt_id"])
                    if attempt["status"] != "open" or attempt["task_id"] != task_dict["task_id"]:
                        errors.append(f"active Attempt is not open: {attempt['attempt_id']}")
                if task_dict["acceptance_head_id"]:
                    try:
                        chain, attempt = self._evaluation_chain(connection, task_dict["acceptance_head_id"])
                        self._validate_acceptance_chain(chain, check_artifacts=False)
                        if attempt["contract_id"] != task_dict["contract_head_id"]:
                            errors.append(f"acceptance contract mismatch: {task_dict['task_id']}")
                    except DurableStateError as exc:
                        errors.append(str(exc))
                if task_dict["lifecycle_status"] == "completed" and not task_dict["acceptance_head_id"]:
                    errors.append(f"completed Task has no acceptance head: {task_dict['task_id']}")
                if task_dict.get("spawned_by_event_id"):
                    origin = self._event(connection, task_dict["spawned_by_event_id"])
                    if origin["project_id"] != task_dict["project_id"]:
                        errors.append(f"Task spawn event project mismatch: {task_dict['task_id']}")
            for recovery_row in connection.execute("SELECT * FROM recovery_views"):
                recovery = dict(recovery_row)
                if content_hash(_json_load(recovery["source_json"], {})) != recovery["source_hash"]:
                    errors.append(f"RecoveryView source hash mismatch: {recovery['task_id']}")
            if project is not None and project["default_task_id"]:
                default_task = self._task(connection, project["default_task_id"])
                latest_attempt = connection.execute(
                    """
                    SELECT * FROM attempts
                    WHERE task_id = ? AND contract_id = ? AND status = 'sealed'
                    ORDER BY started_at DESC, attempt_id DESC LIMIT 1
                    """,
                    (default_task["task_id"], default_task["contract_head_id"]),
                ).fetchone()
                if latest_attempt is not None:
                    workspace_errors.extend(
                        self._live_attempt_evidence_errors(connection, dict(latest_attempt))
                    )
                if default_task["acceptance_head_id"]:
                    try:
                        chain, _ = self._evaluation_chain(connection, default_task["acceptance_head_id"])
                        self._validate_acceptance_chain(chain)
                    except DurableStateError as exc:
                        workspace_errors.append(str(exc))
            all_errors = [*errors, *workspace_errors]
            return {
                "sqlite": sqlite_result,
                "passed": sqlite_result == "ok" and not all_errors,
                "errors": all_errors,
                "reference_errors": errors,
                "workspace_evidence": {
                    "task_id": project["default_task_id"] if project is not None else None,
                    "fresh": not workspace_errors,
                    "errors": workspace_errors,
                },
            }

    def _task(self, connection: sqlite3.Connection, task_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Task not found: {task_id}")
        return dict(row)

    def _contract(self, connection: sqlite3.Connection, contract_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM contract_revisions WHERE contract_id = ?", (contract_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"ContractRevision not found: {contract_id}")
        result = dict(row)
        result["content"] = _json_load(result.pop("content_json"), {})
        return result

    def _attempt(self, connection: sqlite3.Connection, attempt_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Attempt not found: {attempt_id}")
        return dict(row)

    def _evaluation(self, connection: sqlite3.Connection, evaluation_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM evaluations WHERE evaluation_id = ?", (evaluation_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Evaluation not found: {evaluation_id}")
        return dict(row)

    def _cas_task(self, connection: sqlite3.Connection, task_id: str, expected_version: int, fields: dict[str, Any]) -> None:
        allowed = {"lifecycle_status", "contract_head_id", "active_attempt_id", "acceptance_head_id"}
        if not set(fields).issubset(allowed):
            raise ValueError("unsupported Task mutation fields")
        assignments = [f"{key} = ?" for key in fields]
        values = list(fields.values())
        assignments.extend(["state_version = state_version + 1", "updated_at = ?"])
        values.extend([utc_now(), task_id, expected_version])
        cursor = connection.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE task_id = ? AND state_version = ?",
            values,
        )
        if cursor.rowcount != 1:
            current = connection.execute("SELECT state_version FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            current_version = current["state_version"] if current is not None else "missing"
            raise ConflictError(f"task version conflict: expected {expected_version}, current {current_version}")

    def _insert_dependency(self, connection: sqlite3.Connection, task_id: str, dependency_id: str) -> None:
        if task_id == dependency_id:
            raise ValueError("Task cannot depend on itself")
        task = self._task(connection, task_id)
        dependency = self._task(connection, dependency_id)
        if task["project_id"] != dependency["project_id"]:
            raise ValueError("dependency belongs to a different project")
        cycle = connection.execute(
            """
            WITH RECURSIVE reachable(task_id) AS (
                SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ?
                UNION
                SELECT d.depends_on_task_id
                FROM task_dependencies d JOIN reachable r ON d.task_id = r.task_id
            )
            SELECT 1 FROM reachable WHERE task_id = ? LIMIT 1
            """,
            (dependency_id, task_id),
        ).fetchone()
        if cycle is not None:
            raise ValueError("dependency would create a cycle")
        connection.execute("INSERT OR IGNORE INTO task_dependencies(task_id, depends_on_task_id) VALUES (?, ?)", (task_id, dependency_id))

    def _unresolved_dependencies(self, connection: sqlite3.Connection, task_id: str) -> list[str]:
        return [
            str(row["depends_on_task_id"])
            for row in connection.execute(
                """
                SELECT d.depends_on_task_id
                FROM task_dependencies d
                JOIN tasks t ON t.task_id = d.depends_on_task_id
                WHERE d.task_id = ? AND t.lifecycle_status != 'completed'
                ORDER BY d.depends_on_task_id
                """,
                (task_id,),
            )
        ]

    def _task_view(
        self,
        connection: sqlite3.Connection,
        task: dict[str, Any],
        *,
        compact: bool = False,
    ) -> dict[str, Any]:
        dependencies = [str(row[0]) for row in connection.execute("SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ? ORDER BY depends_on_task_id", (task["task_id"],))]
        unresolved = self._unresolved_dependencies(connection, task["task_id"])
        acceptance = {"candidate_evaluation_id": None, "pending_authorities": []}
        if task["lifecycle_status"] != "open":
            readiness = task["lifecycle_status"]
        elif unresolved:
            readiness = "blocked"
        elif task["active_attempt_id"]:
            readiness = "running"
        else:
            acceptance = self._acceptance_state(connection, task)
            if acceptance["candidate_evaluation_id"]:
                readiness = "ready_to_accept"
            elif acceptance["pending_authorities"]:
                readiness = "waiting_review"
            else:
                readiness = "ready"
        result = dict(task)
        result.setdefault("spawned_by_event_id", None)
        result["depends_on"] = dependencies
        result["unresolved_dependencies"] = unresolved
        result["readiness"] = readiness
        result["activity"] = "running" if task["active_attempt_id"] else "idle"
        result["acceptance_candidate_id"] = (
            acceptance["candidate_evaluation_id"] if task["lifecycle_status"] == "open" and not task["active_attempt_id"] and not unresolved else None
        )
        result["pending_authorities"] = (
            acceptance["pending_authorities"] if task["lifecycle_status"] == "open" and not task["active_attempt_id"] and not unresolved else []
        )
        contract = self._contract(connection, task["contract_head_id"]) if task["contract_head_id"] else None
        if compact and contract:
            contract = self._compact_contract(contract)
        result["contract"] = contract
        return result

    def _acceptance_state(self, connection: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
        empty = {"candidate_evaluation_id": None, "pending_authorities": []}
        if not task.get("contract_head_id"):
            return empty
        attempt = connection.execute(
            """
            SELECT * FROM attempts
            WHERE task_id = ? AND contract_id = ? AND status = 'sealed'
            ORDER BY started_at DESC, attempt_id DESC LIMIT 1
            """,
            (task["task_id"], task["contract_head_id"]),
        ).fetchone()
        if attempt is None:
            return empty
        verification = connection.execute(
            """
            SELECT * FROM evaluations
            WHERE task_id = ? AND subject_type = 'attempt' AND subject_id = ?
              AND kind IN ('verification', 'legacy_verification')
            ORDER BY evaluation_seq DESC LIMIT 1
            """,
            (task["task_id"], attempt["attempt_id"]),
        ).fetchone()
        if verification is None:
            return empty
        verification_id = str(verification["evaluation_id"])
        relevant_chains: list[list[dict[str, Any]]] = []
        for row in connection.execute(
            "SELECT * FROM evaluations WHERE task_id = ? ORDER BY evaluation_seq DESC LIMIT 100",
            (task["task_id"],),
        ):
            try:
                chain, root_attempt = self._evaluation_chain(connection, str(row["evaluation_id"]))
            except DurableStateError:
                continue
            if root_attempt["attempt_id"] != attempt["attempt_id"] or chain[-1]["evaluation_id"] != verification_id:
                continue
            relevant_chains.append(chain)
            try:
                self._validate_acceptance_chain(chain, check_artifacts=False)
            except InvalidTransitionError:
                continue
            return {"candidate_evaluation_id": chain[0]["evaluation_id"], "pending_authorities": []}
        root_payload = _json_load(verification["payload_json"], {})
        required = root_payload.get("required_authorities") if isinstance(root_payload, dict) else []
        if not isinstance(required, list):
            required = []
        if not required and verification["decision"] == "review_required":
            required = ["reviewer"]
        if not required and verification["decision"] == "human_acceptance_required":
            required = ["user"]
        present: set[str] = set()
        if relevant_chains:
            present = {
                str(item["authority"])
                for item in relevant_chains[0][:-1]
                if item["decision"] == "approved"
            }
        return {
            "candidate_evaluation_id": None,
            "pending_authorities": sorted({str(item) for item in required if str(item)} - present),
        }

    def _compact_contract(self, contract: dict[str, Any]) -> dict[str, Any]:
        result = dict(contract)
        content = result.get("content")
        if isinstance(content, dict) and len(canonical_json(content).encode("utf-8")) > 16 * 1024:
            result["content"] = {
                "goal": content.get("goal") or content.get("intent") or "",
                "acceptance_criteria": _compact_json(content.get("acceptance_criteria", [])),
                "_truncated": True,
                "content_hash": result.get("content_hash"),
            }
        return result

    def _append_attempt_record(self, connection: sqlite3.Connection, attempt_id: str, record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_payload_size(payload, "Attempt record payload")
        next_seq = int(connection.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM attempt_records WHERE attempt_id = ?", (attempt_id,)).fetchone()[0])
        record_id = new_id("record")
        immutable = {"record_id": record_id, "attempt_id": attempt_id, "seq": next_seq, "type": record_type, "payload": payload, "created_at": utc_now()}
        digest = content_hash(immutable)
        connection.execute(
            "INSERT INTO attempt_records(record_id, attempt_id, seq, type, payload_json, content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record_id, attempt_id, next_seq, record_type, canonical_json(payload), digest, immutable["created_at"]),
        )
        return {**immutable, "content_hash": digest}

    def _attempt_view(
        self,
        connection: sqlite3.Connection,
        attempt: dict[str, Any],
        *,
        record_limit: int | None = None,
        include_evidence: bool = True,
        compact: bool = False,
    ) -> dict[str, Any]:
        result = dict(attempt)
        input_snapshot = _json_load(result.pop("input_snapshot_json"), {})
        manifest = _json_load(result.pop("manifest_json"), None)
        result["input_snapshot"] = _compact_json(input_snapshot) if compact else input_snapshot
        result["manifest"] = self._compact_manifest(manifest) if compact else manifest
        result["record_cursor"] = int(connection.execute("SELECT COALESCE(MAX(seq), 0) FROM attempt_records WHERE attempt_id = ?", (attempt["attempt_id"],)).fetchone()[0])
        result["record_count"] = result["record_cursor"]
        if record_limit == 0:
            record_rows: list[sqlite3.Row] = []
        elif record_limit is None:
            record_rows = list(connection.execute("SELECT * FROM attempt_records WHERE attempt_id = ? ORDER BY seq", (attempt["attempt_id"],)))
        else:
            record_rows = list(
                reversed(
                    list(
                        connection.execute(
                            "SELECT * FROM attempt_records WHERE attempt_id = ? ORDER BY seq DESC LIMIT ?",
                            (attempt["attempt_id"], max(1, record_limit)),
                        )
                    )
                )
            )
        result["records"] = [
            {
                **dict(row),
                "payload": _compact_json(_json_load(row["payload_json"], {}))
                if compact
                else _json_load(row["payload_json"], {}),
            }
            for row in record_rows
        ]
        for item in result["records"]:
            item.pop("payload_json", None)
        result["evidence_count"] = int(connection.execute("SELECT COUNT(*) FROM evidence WHERE attempt_id = ?", (attempt["attempt_id"],)).fetchone()[0])
        evidence = (
            [dict(row) for row in connection.execute("SELECT * FROM evidence WHERE attempt_id = ? ORDER BY created_at, evidence_id", (attempt["attempt_id"],))]
            if include_evidence
            else []
        )
        if compact:
            for item in evidence:
                if len(str(item.get("description") or "").encode("utf-8")) > 1024:
                    item["description"] = str(item["description"])[:1024]
        result["evidence"] = evidence
        return result

    def _compact_manifest(self, manifest: Any) -> Any:
        if not isinstance(manifest, dict):
            return manifest
        header = manifest.get("header") if isinstance(manifest.get("header"), dict) else {}
        records = manifest.get("records") if isinstance(manifest.get("records"), list) else []
        evidence = manifest.get("evidence") if isinstance(manifest.get("evidence"), list) else []
        return {
            "attempt_id": header.get("attempt_id"),
            "task_id": header.get("task_id"),
            "contract_id": header.get("contract_id"),
            "outcome": manifest.get("outcome"),
            "record_count": len(records),
            "evidence_count": len(evidence),
            "content_hash": content_hash(manifest),
            "_compact": True,
        }

    def _insert_evaluation(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        subject_type: str,
        subject_id: str,
        subject_hash: str,
        kind: str,
        authority: str,
        evaluator: str,
        evaluator_version: str,
        decision: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        _ensure_payload_size(payload, "Evaluation payload")
        if decision not in EVALUATION_DECISIONS:
            raise ValueError(f"unknown evaluation decision: {decision}")
        evaluation_id = new_id("evaluation")
        created_at = utc_now()
        immutable = {
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_hash": subject_hash,
            "kind": kind,
            "authority": authority,
            "evaluator": evaluator,
            "evaluator_version": evaluator_version,
            "decision": decision,
            "payload": payload,
            "created_at": created_at,
        }
        digest = content_hash(immutable)
        connection.execute(
            """
            INSERT INTO evaluations(
                evaluation_id, task_id, subject_type, subject_id, subject_hash,
                kind, authority, evaluator, evaluator_version, decision,
                payload_json, content_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                task_id,
                subject_type,
                subject_id,
                subject_hash,
                kind,
                authority,
                evaluator,
                evaluator_version,
                decision,
                canonical_json(payload),
                digest,
                created_at,
            ),
        )
        task = self._task(connection, task_id)
        self._append_event(
            connection,
            project_id=task["project_id"],
            scope="task",
            task_id=task_id,
            evaluation_id=evaluation_id,
            event_type="evaluation_recorded",
            summary=f"Recorded {kind} Evaluation {evaluation_id}: {decision}.",
            decision=decision,
            payload={"subject_type": subject_type, "subject_id": subject_id, "content_hash": digest},
        )
        return self._evaluation_view(connection, self._evaluation(connection, evaluation_id))

    def _evaluation_view(
        self,
        connection: sqlite3.Connection,
        evaluation: dict[str, Any],
        *,
        compact: bool = False,
    ) -> dict[str, Any]:
        result = dict(evaluation)
        payload = _json_load(result.pop("payload_json"), {})
        result["payload"] = self._compact_evaluation_payload(payload) if compact else payload
        return result

    def _compact_evaluation_payload(self, payload: Any) -> Any:
        if len(canonical_json(payload).encode("utf-8")) <= MAX_RECOVERY_PAYLOAD_BYTES:
            return payload
        result: dict[str, Any] = {
            "_truncated": True,
            "content_hash": content_hash(payload),
            "bytes": len(canonical_json(payload).encode("utf-8")),
        }
        if isinstance(payload, dict):
            for key in ["verification_spec_hash", "required_authorities", "artifact_bindings", "bound_to_execution"]:
                if key in payload:
                    result[key] = _compact_json(payload[key])
            validator_results = payload.get("validator_results")
            if isinstance(validator_results, list):
                result["validator_summary"] = {
                    "count": len(validator_results),
                    "passed": sum(1 for item in validator_results if isinstance(item, dict) and item.get("passed")),
                    "failed": sum(1 for item in validator_results if isinstance(item, dict) and not item.get("passed")),
                }
        return result

    def _evaluation_chain(self, connection: sqlite3.Connection, evaluation_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current = self._evaluation(connection, evaluation_id)
        while True:
            if current["evaluation_id"] in seen:
                raise DurableStateError("Evaluation chain contains a cycle")
            seen.add(current["evaluation_id"])
            expected_hash = content_hash(
                {
                    "evaluation_id": current["evaluation_id"],
                    "task_id": current["task_id"],
                    "subject_type": current["subject_type"],
                    "subject_id": current["subject_id"],
                    "subject_hash": current["subject_hash"],
                    "kind": current["kind"],
                    "authority": current["authority"],
                    "evaluator": current["evaluator"],
                    "evaluator_version": current["evaluator_version"],
                    "decision": current["decision"],
                    "payload": _json_load(current["payload_json"], {}),
                    "created_at": current["created_at"],
                }
            )
            if expected_hash != current["content_hash"]:
                raise DurableStateError(f"Evaluation hash mismatch: {current['evaluation_id']}")
            chain.append(current)
            if current["subject_type"] == "attempt":
                attempt = self._attempt(connection, current["subject_id"])
                if current["task_id"] != attempt["task_id"]:
                    raise DurableStateError("Evaluation task does not match its Attempt subject")
                self._assert_attempt_content(connection, attempt, phase="Evaluation chain resolution")
                if attempt["status"] != "sealed" or attempt["execution_hash"] != current["subject_hash"]:
                    raise DurableStateError("Evaluation does not bind the current immutable Attempt content")
                return chain, attempt
            if current["subject_type"] != "evaluation":
                raise DurableStateError(f"unsupported Evaluation subject: {current['subject_type']}")
            subject = self._evaluation(connection, current["subject_id"])
            if current["task_id"] != subject["task_id"]:
                raise DurableStateError("Review task does not match its Evaluation subject")
            if subject["content_hash"] != current["subject_hash"]:
                raise DurableStateError("Review subject hash does not match the referenced Evaluation")
            current = subject

    def _root_attempt_for_evaluation(self, connection: sqlite3.Connection, evaluation: dict[str, Any]) -> dict[str, Any]:
        _, attempt = self._evaluation_chain(connection, evaluation["evaluation_id"])
        return attempt

    def _build_attempt_manifest(
        self,
        connection: sqlite3.Connection,
        attempt: dict[str, Any],
        *,
        outcome: str,
    ) -> dict[str, Any]:
        records = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM attempt_records WHERE attempt_id = ? ORDER BY seq",
                (attempt["attempt_id"],),
            )
        ]
        evidence = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM evidence WHERE attempt_id = ? ORDER BY created_at, evidence_id",
                (attempt["attempt_id"],),
            )
        ]
        header = {
            key: attempt[key]
            for key in [
                "attempt_id",
                "task_id",
                "contract_id",
                "plan",
                "plan_hash",
                "input_hash",
                "attempt_fingerprint",
                "retry_of_attempt_id",
                "retry_reason",
                "actor",
                "started_at",
            ]
        }
        return {
            "header": header,
            "outcome": outcome,
            "records": [
                {"seq": item["seq"], "type": item["type"], "content_hash": item["content_hash"]}
                for item in records
            ],
            "evidence": [
                {"evidence_id": item["evidence_id"], "path": item["path"], "sha256": item["sha256"]}
                for item in evidence
            ],
        }

    def _live_attempt_evidence_errors(self, connection: sqlite3.Connection, attempt: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for item in connection.execute(
            "SELECT path, sha256 FROM evidence WHERE attempt_id = ? ORDER BY created_at, evidence_id",
            (attempt["attempt_id"],),
        ):
            target = Path(str(item["path"])).expanduser()
            if not target.is_absolute():
                target = (self.workspace / target).resolve()
            if not target.is_file():
                errors.append(f"evidence missing: {item['path']}")
            elif file_hash(target) != item["sha256"]:
                errors.append(f"evidence hash drift: {item['path']}")
        return errors

    def _assert_live_attempt_evidence(
        self,
        connection: sqlite3.Connection,
        attempt: dict[str, Any],
        *,
        phase: str,
    ) -> None:
        errors = self._live_attempt_evidence_errors(connection, attempt)
        if errors:
            raise InvalidTransitionError(f"Attempt evidence changed before {phase}: " + "; ".join(errors))

    def _attempt_content_errors(self, connection: sqlite3.Connection, attempt: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        attempt_id = str(attempt["attempt_id"])
        input_snapshot = _json_load(attempt.get("input_snapshot_json"), {})
        if content_hash(input_snapshot) != attempt["input_hash"]:
            errors.append(f"Attempt input hash mismatch: {attempt_id}")
        if content_hash({"plan": str(attempt["plan"]).casefold()}) != attempt["plan_hash"]:
            errors.append(f"Attempt plan hash mismatch: {attempt_id}")
        contract = self._contract(connection, attempt["contract_id"])
        expected_fingerprint = content_hash(
            {
                "contract_hash": contract["content_hash"],
                "plan_hash": attempt["plan_hash"],
                "input_hash": attempt["input_hash"],
            }
        )
        if expected_fingerprint != attempt["attempt_fingerprint"]:
            errors.append(f"Attempt fingerprint mismatch: {attempt_id}")
        for expected_seq, row in enumerate(
            connection.execute("SELECT * FROM attempt_records WHERE attempt_id = ? ORDER BY seq", (attempt_id,)),
            start=1,
        ):
            record = dict(row)
            immutable = {
                "record_id": record["record_id"],
                "attempt_id": record["attempt_id"],
                "seq": record["seq"],
                "type": record["type"],
                "payload": _json_load(record["payload_json"], {}),
                "created_at": record["created_at"],
            }
            if record["seq"] != expected_seq:
                errors.append(f"Attempt record sequence gap: {attempt_id}")
            if content_hash(immutable) != record["content_hash"]:
                errors.append(f"Attempt record hash mismatch: {record['record_id']}")
        if attempt["status"] == "sealed":
            manifest = _json_load(attempt.get("manifest_json"), None)
            if not isinstance(manifest, dict):
                errors.append(f"sealed Attempt has no manifest: {attempt_id}")
            else:
                expected_manifest = self._build_attempt_manifest(
                    connection,
                    attempt,
                    outcome=str(manifest.get("outcome") or ""),
                )
                if manifest != expected_manifest:
                    errors.append(f"Attempt manifest mismatch: {attempt_id}")
                if content_hash(manifest) != attempt["execution_hash"]:
                    errors.append(f"Attempt execution hash mismatch: {attempt_id}")
        return errors

    def _assert_attempt_content(
        self,
        connection: sqlite3.Connection,
        attempt: dict[str, Any],
        *,
        phase: str,
    ) -> None:
        errors = self._attempt_content_errors(connection, attempt)
        if errors:
            raise InvalidTransitionError(f"Attempt content changed before {phase}: " + "; ".join(errors))

    def _validate_acceptance_chain(self, chain: list[dict[str, Any]], *, check_artifacts: bool = True) -> None:
        terminal = chain[0]
        root = chain[-1]
        if terminal["decision"] != "approved":
            raise InvalidTransitionError("terminal Evaluation must be approved")
        if root["kind"] not in {"verification", "legacy_verification"}:
            raise InvalidTransitionError("acceptance chain must terminate at a verification Evaluation")
        if root["decision"] == "legacy_unbound":
            raise InvalidTransitionError("legacy_unbound evidence cannot grant v2 acceptance")
        if root["decision"] in {"rejected", "needs_changes", "unsupported"}:
            raise InvalidTransitionError(f"root verification decision is {root['decision']}")
        overlays = chain[:-1]
        if any(item["decision"] != "approved" for item in overlays):
            raise InvalidTransitionError("every authority overlay in the selected acceptance chain must be approved")
        if root["decision"] not in {"approved", "review_required", "human_acceptance_required"}:
            raise InvalidTransitionError(f"root verification decision cannot grant acceptance: {root['decision']}")
        payload = _json_load(root.get("payload_json"), {})
        required = payload.get("required_authorities") if isinstance(payload, dict) else None
        if not isinstance(required, list):
            required = []
            if root["decision"] == "review_required":
                required.append("reviewer")
            if root["decision"] == "human_acceptance_required":
                required.append("user")
        approved_authorities = {str(item["authority"]) for item in overlays if item["decision"] == "approved"}
        missing = sorted({str(item) for item in required if str(item)} - approved_authorities)
        if missing:
            raise InvalidTransitionError("verification still requires authority: " + ", ".join(missing))
        if not check_artifacts:
            return
        for binding in payload.get("artifact_bindings", []) if isinstance(payload, dict) else []:
            if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
                continue
            current = self._one_artifact_binding(binding["path"])
            if current != binding:
                raise InvalidTransitionError(f"verified artifact changed after Evaluation: {binding['path']}")

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        scope: str,
        event_type: str,
        summary: str,
        task_id: str | None = None,
        attempt_id: str | None = None,
        evaluation_id: str | None = None,
        diagnosis: str = "",
        decision: str = "",
        next_plan: str = "",
        supersedes_event_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _ensure_payload_size(payload or {}, "DecisionEvent payload")
        event_id = new_id("event")
        created_at = utc_now()
        immutable = {
            "event_id": event_id,
            "project_id": project_id,
            "scope": scope,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "evaluation_id": evaluation_id,
            "type": event_type,
            "summary": summary,
            "diagnosis": diagnosis.strip(),
            "decision": decision.strip(),
            "next_plan": next_plan.strip(),
            "supersedes_event_id": supersedes_event_id,
            "payload": payload or {},
            "created_at": created_at,
        }
        digest = content_hash(immutable)
        cursor = connection.execute(
            """
            INSERT INTO decision_events(
                event_id, project_id, scope, task_id, attempt_id, evaluation_id,
                type, summary, diagnosis, decision, next_plan,
                supersedes_event_id, payload_json, content_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                project_id,
                scope,
                task_id,
                attempt_id,
                evaluation_id,
                event_type,
                summary,
                diagnosis.strip(),
                decision.strip(),
                next_plan.strip(),
                supersedes_event_id,
                canonical_json(payload or {}),
                digest,
                created_at,
            ),
        )
        return {**immutable, "event_seq": int(cursor.lastrowid), "content_hash": digest}

    def _event(self, connection: sqlite3.Connection, event_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM decision_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"DecisionEvent not found: {event_id}")
        return dict(row)

    def _event_view(self, event: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
        result = dict(event)
        payload = _json_load(result.pop("payload_json"), {})
        result["payload"] = _compact_json(payload) if compact else payload
        if compact:
            for key in ["summary", "diagnosis", "decision", "next_plan"]:
                result[key] = _truncate_text(str(result.get(key) or ""), 2048)
        return result

    def _current_decisions(
        self,
        connection: sqlite3.Connection,
        task: dict[str, Any],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in SYSTEM_EVENT_TYPES)
        rows = list(
            connection.execute(
                f"""
                SELECT e.* FROM decision_events e
                WHERE (e.task_id = ? OR (e.project_id = ? AND e.scope = 'project'))
                  AND e.type NOT IN ({placeholders})
                  AND NOT EXISTS (
                      SELECT 1 FROM decision_events newer
                      WHERE newer.supersedes_event_id = e.event_id
                  )
                ORDER BY e.event_seq DESC
                LIMIT ?
                """,
                (task["task_id"], task["project_id"], *sorted(SYSTEM_EVENT_TYPES), max(1, limit)),
            )
        )
        return [self._event_view(dict(row), compact=True) for row in reversed(rows)]

    def _thread_assignment_view(self, assignment: dict[str, Any]) -> dict[str, Any]:
        result = dict(assignment)
        result["focus_stack"] = _json_load(result.pop("focus_stack_json"), [])
        return result

    def _recovery_source(self, connection: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
        contract_hash = ""
        if task["contract_head_id"]:
            contract_hash = self._contract(connection, task["contract_head_id"])["content_hash"]
        active_cursor = 0
        if task["active_attempt_id"]:
            active_cursor = int(connection.execute("SELECT COALESCE(MAX(seq), 0) FROM attempt_records WHERE attempt_id = ?", (task["active_attempt_id"],)).fetchone()[0])
        latest_attempts = [str(row[0]) for row in connection.execute("SELECT attempt_id FROM attempts WHERE task_id = ? ORDER BY started_at DESC LIMIT 3", (task["task_id"],))]
        latest_evaluations = [str(row[0]) for row in connection.execute("SELECT evaluation_id FROM evaluations WHERE task_id = ? ORDER BY evaluation_seq DESC LIMIT 5", (task["task_id"],))]
        latest_task_event = int(connection.execute("SELECT COALESCE(MAX(event_seq), 0) FROM decision_events WHERE task_id = ?", (task["task_id"],)).fetchone()[0])
        latest_project_event = int(connection.execute("SELECT COALESCE(MAX(event_seq), 0) FROM decision_events WHERE project_id = ? AND scope = 'project'", (task["project_id"],)).fetchone()[0])
        dependency_refs = [
            {
                "task_id": str(row["task_id"]),
                "state_version": int(row["state_version"]),
                "lifecycle_status": str(row["lifecycle_status"]),
                "acceptance_head_id": row["acceptance_head_id"],
            }
            for row in connection.execute(
                """
                SELECT t.task_id, t.state_version, t.lifecycle_status, t.acceptance_head_id
                FROM task_dependencies d
                JOIN tasks t ON t.task_id = d.depends_on_task_id
                WHERE d.task_id = ?
                ORDER BY t.task_id
                """,
                (task["task_id"],),
            )
        ]
        return {
            "task_id": task["task_id"],
            "task_state_version": task["state_version"],
            "contract_head_ref": {"id": task["contract_head_id"], "hash": contract_hash},
            "active_attempt_ref": {"id": task["active_attempt_id"], "event_cursor": active_cursor},
            "acceptance_head_id": task["acceptance_head_id"],
            "dependency_refs": dependency_refs,
            "latest_attempt_refs": latest_attempts,
            "latest_evaluation_refs": latest_evaluations,
            "latest_task_event_seq": latest_task_event,
            "latest_project_event_seq": latest_project_event,
        }

    def _recovery_bundle(self, connection: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
        current_source = self._recovery_source(connection, task)
        current_hash = content_hash(current_source)
        saved = connection.execute("SELECT * FROM recovery_views WHERE task_id = ?", (task["task_id"],)).fetchone()
        if saved is None:
            status = "incomplete"
            saved_source: dict[str, Any] = {}
            saved_hash = ""
            resume = ""
        else:
            saved_source = _json_load(saved["source_json"], {})
            saved_hash = str(saved["source_hash"])
            resume = str(saved["resume_markdown"])
            status = "fresh" if saved_hash == current_hash else "stale"
        task_event_seq = int(saved_source.get("latest_task_event_seq", 0))
        project_event_seq = int(saved_source.get("latest_project_event_seq", 0))
        delta_rows = list(connection.execute(
            """
            SELECT * FROM decision_events
            WHERE (task_id = ? AND event_seq > ?)
               OR (project_id = ? AND scope = 'project' AND event_seq > ?)
            ORDER BY event_seq
            LIMIT 101
            """,
            (task["task_id"], task_event_seq, task["project_id"], project_event_seq),
        ))
        delta_truncated = len(delta_rows) > 100
        delta_rows = delta_rows[:100]
        delta_events = []
        for row in delta_rows:
            delta_events.append(self._event_view(dict(row), compact=True))
        active_attempt = (
            self._attempt_view(
                connection,
                self._attempt(connection, task["active_attempt_id"]),
                record_limit=100,
                compact=True,
            )
            if task["active_attempt_id"]
            else None
        )
        acceptance_chain: list[dict[str, Any]] = []
        if task["acceptance_head_id"]:
            chain, _ = self._evaluation_chain(connection, task["acceptance_head_id"])
            acceptance_chain = [self._evaluation_view(connection, item, compact=True) for item in chain]
        current_decisions = self._current_decisions(connection, task, limit=20)
        return {
            "status": status,
            "source_hash": current_hash,
            "saved_source_hash": saved_hash,
            "current_source": current_source,
            "saved_source": saved_source,
            "task": self._task_view(connection, task, compact=True),
            "active_attempt": active_attempt,
            "latest_attempts": [
                self._attempt_view(
                    connection,
                    self._attempt(connection, item),
                    record_limit=0,
                    include_evidence=False,
                    compact=True,
                )
                for item in current_source["latest_attempt_refs"]
            ],
            "latest_evaluations": [
                self._evaluation_view(connection, self._evaluation(connection, item), compact=True)
                for item in current_source["latest_evaluation_refs"]
            ],
            "acceptance_chain": acceptance_chain,
            "current_decisions": current_decisions,
            "delta_events": delta_events,
            "delta_events_truncated": delta_truncated,
            "resume_markdown": resume,
        }

    def _artifact_bindings(self, validators: list[Any]) -> list[dict[str, Any]]:
        paths = sorted(
            {
                str(validator["path"])
                for validator in validators
                if isinstance(validator, dict) and isinstance(validator.get("path"), str) and validator["path"]
            }
        )
        return [self._one_artifact_binding(path) for path in paths]

    def _one_artifact_binding(self, path: str) -> dict[str, Any]:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = (self.workspace / target).resolve()
        if target.is_file():
            return {"path": path, "state": "file", "sha256": file_hash(target)}
        if target.is_dir():
            return {"path": path, "state": "directory", "sha256": ""}
        return {"path": path, "state": "missing", "sha256": ""}

    def _default_resume(self, connection: sqlite3.Connection, task: dict[str, Any], source: dict[str, Any]) -> str:
        contract = self._contract(connection, task["contract_head_id"]) if task["contract_head_id"] else None
        goal = _truncate_text(str(contract["content"].get("goal", "")), 8192) if contract else ""
        decisions = self._current_decisions(connection, task, limit=20)
        task_decisions = [item for item in decisions if item["scope"] == "task"]
        project_decisions = [item for item in decisions if item["scope"] == "project"]
        latest = task_decisions[-1] if task_decisions else None
        project_lines = [f"- [{item['type']}] {item['summary']}" for item in project_decisions] or ["- None recorded."]
        task_lines = [f"- [{item['type']}] {item['summary']}" for item in task_decisions] or ["- None recorded."]
        return "\n".join(
            [
                "# Resume Brief",
                "",
                "## Task",
                "",
                f"- ID: {task['task_id']}",
                f"- Title: {task['title']}",
                f"- Lifecycle: {task['lifecycle_status']}",
                "",
                "## Goal",
                "",
                f"- {goal or 'No locked ContractRevision.'}",
                "",
                "## Active Attempt",
                "",
                f"- {task['active_attempt_id'] or 'None'}",
                "",
                "## Latest Diagnosis",
                "",
                f"- {(latest.get('diagnosis') if latest else '') or 'None recorded.'}",
                "",
                "## Decision",
                "",
                f"- {(latest.get('decision') if latest else '') or 'None recorded.'}",
                "",
                "## Next Plan",
                "",
                f"- {(latest.get('next_plan') if latest else '') or 'Inspect the bounded recovery bundle.'}",
                "",
                "## Current Project Decisions",
                "",
                *project_lines,
                "",
                "## Current Task Decisions",
                "",
                *task_lines,
                "",
                "## Recovery Source",
                "",
                f"- {content_hash(source)}",
            ]
        )

    def _validate_contract(self, content: dict[str, Any]) -> None:
        if not isinstance(content, dict):
            raise ValueError("ContractRevision content must be a JSON object")
        _ensure_payload_size(content, "ContractRevision content")
        goal = content.get("goal") or content.get("intent")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("ContractRevision requires a non-empty goal")
        for key in ["constraints", "non_goals", "acceptance_criteria"]:
            if key in content and not isinstance(content[key], list):
                raise ValueError(f"ContractRevision {key} must be a list")
        if not isinstance(content.get("verification_spec"), dict):
            raise ValueError("ContractRevision requires verification_spec")


def _manual_authority(validator: dict[str, Any]) -> str:
    if validator.get("requires_user_confirmation") is True:
        return "user"
    if str(validator.get("authority") or "").casefold() == "user":
        return "user"
    if str(validator.get("reviewer") or "").casefold() in {"user", "human", "human_operator"}:
        return "user"
    if validator.get("delegable") is False:
        return "user"
    return "reviewer"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _ensure_payload_size(payload: Any, label: str) -> None:
    size = len(canonical_json(payload).encode("utf-8"))
    if size > MAX_STORED_PAYLOAD_BYTES:
        raise ValueError(f"{label} exceeds {MAX_STORED_PAYLOAD_BYTES} bytes")


def _compact_json(payload: Any) -> Any:
    encoded = canonical_json(payload).encode("utf-8")
    if len(encoded) <= MAX_RECOVERY_PAYLOAD_BYTES:
        return payload
    return {
        "_truncated": True,
        "content_hash": content_hash(payload),
        "bytes": len(encoded),
    }


def _truncate_text(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "..."


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    workspace TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL,
    default_task_id TEXT,
    state_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    title TEXT NOT NULL,
    parent_task_id TEXT REFERENCES tasks(task_id),
    spawned_by_event_id TEXT REFERENCES decision_events(event_id),
    lifecycle_status TEXT NOT NULL CHECK(lifecycle_status IN ('open', 'paused', 'completed', 'cancelled')),
    state_version INTEGER NOT NULL,
    contract_head_id TEXT,
    active_attempt_id TEXT,
    acceptance_head_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(task_id),
    PRIMARY KEY(task_id, depends_on_task_id),
    CHECK(task_id != depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS contract_revisions (
    contract_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    revision INTEGER NOT NULL,
    parent_contract_id TEXT REFERENCES contract_revisions(contract_id),
    content_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    UNIQUE(task_id, revision),
    UNIQUE(contract_id, content_hash)
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    contract_id TEXT NOT NULL REFERENCES contract_revisions(contract_id),
    status TEXT NOT NULL CHECK(status IN ('open', 'sealed', 'aborted')),
    plan TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    attempt_fingerprint TEXT NOT NULL,
    retry_of_attempt_id TEXT REFERENCES attempts(attempt_id),
    retry_reason TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL,
    started_at TEXT NOT NULL,
    sealed_at TEXT,
    execution_hash TEXT,
    manifest_json TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_attempt_per_task
ON attempts(task_id) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS attempts_by_task ON attempts(task_id, started_at);
CREATE INDEX IF NOT EXISTS attempts_by_fingerprint ON attempts(task_id, attempt_fingerprint);

CREATE TABLE IF NOT EXISTS attempt_records (
    record_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(attempt_id, seq)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    subject_type TEXT NOT NULL CHECK(subject_type IN ('attempt', 'evaluation')),
    subject_id TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    authority TEXT NOT NULL,
    evaluator TEXT NOT NULL,
    evaluator_version TEXT NOT NULL,
    decision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS evaluations_by_task ON evaluations(task_id, evaluation_seq);

CREATE TABLE IF NOT EXISTS decision_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    scope TEXT NOT NULL CHECK(scope IN ('project', 'task')),
    task_id TEXT REFERENCES tasks(task_id),
    attempt_id TEXT REFERENCES attempts(attempt_id),
    evaluation_id TEXT REFERENCES evaluations(evaluation_id),
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    diagnosis TEXT NOT NULL,
    decision TEXT NOT NULL,
    next_plan TEXT NOT NULL,
    supersedes_event_id TEXT REFERENCES decision_events(event_id),
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK((scope = 'project' AND task_id IS NULL) OR (scope = 'task' AND task_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS events_by_task ON decision_events(task_id, event_seq);
CREATE INDEX IF NOT EXISTS events_by_project ON decision_events(project_id, scope, event_seq);

CREATE TABLE IF NOT EXISTS recovery_views (
    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
    source_json TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    resume_markdown TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thread_assignments (
    thread_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    focus_stack_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


_REBUILD_DECISION_EVENTS_WITH_EVALUATION_FK = """
BEGIN IMMEDIATE;
ALTER TABLE decision_events RENAME TO decision_events_v1;
CREATE TABLE decision_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    scope TEXT NOT NULL CHECK(scope IN ('project', 'task')),
    task_id TEXT REFERENCES tasks(task_id),
    attempt_id TEXT REFERENCES attempts(attempt_id),
    evaluation_id TEXT REFERENCES evaluations(evaluation_id),
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    diagnosis TEXT NOT NULL,
    decision TEXT NOT NULL,
    next_plan TEXT NOT NULL,
    supersedes_event_id TEXT REFERENCES decision_events(event_id),
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK((scope = 'project' AND task_id IS NULL) OR (scope = 'task' AND task_id IS NOT NULL))
);
INSERT INTO decision_events(
    event_seq, event_id, project_id, scope, task_id, attempt_id, evaluation_id,
    type, summary, diagnosis, decision, next_plan, supersedes_event_id,
    payload_json, content_hash, created_at
)
SELECT
    event_seq, event_id, project_id, scope, task_id, attempt_id, evaluation_id,
    type, summary, diagnosis, decision, next_plan, supersedes_event_id,
    payload_json, content_hash, created_at
FROM decision_events_v1;
DROP TABLE decision_events_v1;
CREATE INDEX events_by_task ON decision_events(task_id, event_seq);
CREATE INDEX events_by_project ON decision_events(project_id, scope, event_seq);
COMMIT;
"""
