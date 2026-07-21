from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Iterator
import uuid

from metaloop_core.contracts import contract_assurance, contract_hash, managed_output_paths, normalize_contract, validate_contract, verify_stable_inputs
from metaloop_core.schemas import (
    ASSURANCE_LEVELS,
    ATTEMPT_SCHEMA,
    ATTEMPT_STATES,
    CHECKPOINT_SCHEMA,
    DECISION_SCHEMA,
    DECISION_TYPES,
    DECISIONS,
    EVALUATION_DECISIONS,
    EVALUATION_SCHEMA,
    EVIDENCE_SCHEMA,
    PROJECT_SCHEMA,
    PROTOCOL_VERSION,
    RECOVERY_SCHEMA,
    SCHEMA_VERSION,
    TASK_SCHEMA,
    TASK_STATES,
)
from metaloop_core.workspace import GitWorkspace, WorkspaceStamp, alignment_reason, changed_paths_between, compare_stamps, path_allowed


class DurableError(RuntimeError):
    pass


class ConflictError(DurableError):
    pass


class NotFoundError(DurableError):
    pass


class InvalidTransitionError(DurableError):
    pass


class DuplicateAttemptError(DurableError):
    pass


AUTHORITY_SEQUENCE = ("reviewer", "user")


@dataclass(frozen=True)
class ProjectRef:
    project_id: str
    repository_root: str
    worktree_path: str


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class DurableStore:
    """Canonical v3 SQLite store with compatible v3.2 protocol semantics."""

    def __init__(self, workspace: str | Path = ".", *, initialize: bool = False) -> None:
        requested = Path(workspace).expanduser().resolve()
        try:
            self.workspace = Path(GitWorkspace(requested).identity().worktree_path)
        except (OSError, RuntimeError):
            self.workspace = requested
        self.db_path = self.workspace / ".metaloop" / "metaloop.db"
        if initialize:
            self.initialize()
        if not self.db_path.exists():
            raise DurableError("v3 Project is not initialized; run project init")
        self.conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        version = self._meta("schema_version")
        if version != str(SCHEMA_VERSION):
            raise DurableError(f"unsupported MetaLoop schema {version or 'unknown'}; v3 requires schema {SCHEMA_VERSION}")

    def initialize(self) -> ProjectRef:
        if self.db_path.exists():
            try:
                existing = sqlite3.connect(self.db_path)
                version = existing.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                existing.close()
            except sqlite3.Error:
                version = None
            if version and str(version[0]) == str(SCHEMA_VERSION):
                raise DurableError("v3 Project already initialized")
            raise DurableError("existing non-v3 MetaLoop state must be archived before clean-cut initialization")
        identity = GitWorkspace(self.workspace).identity()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema(conn)
        project_id = new_id("project")
        now = utc_now()
        conn.execute("INSERT INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        conn.execute(
            "INSERT INTO projects(project_id,schema,version,repository_root,worktree_path,adapter,adapter_version,state_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (project_id, PROJECT_SCHEMA, "1.0", identity.repository_root, identity.worktree_path, identity.adapter, identity.adapter_version, 1, now, now),
        )
        conn.close()
        return ProjectRef(project_id, identity.repository_root, identity.worktree_path)

    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE projects(
                project_id TEXT PRIMARY KEY, schema TEXT NOT NULL, version TEXT NOT NULL,
                repository_root TEXT NOT NULL, worktree_path TEXT NOT NULL UNIQUE,
                adapter TEXT NOT NULL, adapter_version TEXT NOT NULL,
                default_task_id TEXT, state_version INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE tasks(
                task_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
                schema TEXT NOT NULL, version TEXT NOT NULL, title TEXT NOT NULL,
                parent_task_id TEXT REFERENCES tasks(task_id), lifecycle_status TEXT NOT NULL,
                state_version INTEGER NOT NULL, contract_head_id TEXT, active_attempt_id TEXT,
                acceptance_head_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE task_dependencies(task_id TEXT NOT NULL REFERENCES tasks(task_id), depends_on TEXT NOT NULL REFERENCES tasks(task_id), PRIMARY KEY(task_id,depends_on));
            CREATE TABLE contracts(
                contract_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
                revision INTEGER NOT NULL, parent_contract_id TEXT REFERENCES contracts(contract_id),
                schema TEXT NOT NULL, content_json TEXT NOT NULL, content_hash TEXT NOT NULL,
                locked_at TEXT NOT NULL, UNIQUE(task_id,revision)
            );
            CREATE TABLE attempts(
                attempt_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
                contract_id TEXT NOT NULL REFERENCES contracts(contract_id), schema TEXT NOT NULL,
                status TEXT NOT NULL, plan TEXT NOT NULL, plan_hash TEXT NOT NULL,
                input_json TEXT NOT NULL, input_hash TEXT NOT NULL, fingerprint TEXT NOT NULL,
                baseline_stamp_json TEXT NOT NULL, baseline_stamp_hash TEXT NOT NULL,
                latest_checkpoint_hash TEXT, execution_hash TEXT,
                started_at TEXT NOT NULL, sealed_at TEXT, UNIQUE(task_id,fingerprint)
            );
            CREATE TABLE attempt_records(
                record_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                seq INTEGER NOT NULL, type TEXT NOT NULL, content_json TEXT NOT NULL,
                content_hash TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(attempt_id,seq)
            );
            CREATE TABLE evidence(
                evidence_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                path TEXT NOT NULL, sha256 TEXT NOT NULL, media_type TEXT NOT NULL,
                description TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE decision_events(
                event_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
                task_id TEXT REFERENCES tasks(task_id), attempt_id TEXT REFERENCES attempts(attempt_id),
                scope TEXT NOT NULL, type TEXT NOT NULL, summary TEXT NOT NULL, diagnosis TEXT NOT NULL,
                decision TEXT NOT NULL, next_plan TEXT NOT NULL, payload_json TEXT NOT NULL,
                content_hash TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE evaluations(
                evaluation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
                subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, subject_hash TEXT NOT NULL,
                kind TEXT NOT NULL, authority TEXT NOT NULL, evaluator TEXT NOT NULL,
                evaluator_version TEXT NOT NULL, decision TEXT NOT NULL, content_json TEXT NOT NULL,
                content_hash TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE recovery_views(
                task_id TEXT PRIMARY KEY REFERENCES tasks(task_id), schema TEXT NOT NULL,
                source_hash TEXT NOT NULL, workspace_alignment TEXT NOT NULL,
                resume_markdown TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE thread_assignments(thread_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), role TEXT NOT NULL, assigned_at TEXT NOT NULL);
            CREATE INDEX attempts_task_status ON attempts(task_id,status);
            CREATE INDEX attempt_records_attempt_seq ON attempt_records(attempt_id,seq);
            CREATE INDEX evidence_attempt_path ON evidence(attempt_id,path);
            CREATE INDEX decisions_task_created ON decision_events(task_id,created_at);
            """
        )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            yield self.conn
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self.conn.close()

    def project(self) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM projects LIMIT 1").fetchone()
        if row is None:
            raise DurableError("Project row missing")
        value = dict(row)
        value["schema_version"] = int(self._meta("schema_version") or 0)
        return value

    def project_id(self) -> str:
        return str(self.project()["project_id"])

    def task(self, task_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Task not found: {task_id}")
        value = dict(row)
        value["active_evaluation_head_id"] = value.get("acceptance_head_id")
        value["depends_on"] = [item[0] for item in self.conn.execute("SELECT depends_on FROM task_dependencies WHERE task_id=? ORDER BY depends_on", (task_id,))]
        return value

    def tasks(self) -> list[dict[str, Any]]:
        return [self.task(row[0]) for row in self.conn.execute("SELECT task_id FROM tasks ORDER BY created_at")]

    def create_task(self, title: str, *, parent_task_id: str | None = None, depends_on: list[str] | None = None) -> dict[str, Any]:
        if not title.strip():
            raise ValueError("task title is required")
        project_id = self.project_id()
        if parent_task_id:
            self.task(parent_task_id)
        task_id = new_id("task")
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO tasks(task_id,project_id,schema,version,title,parent_task_id,lifecycle_status,state_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (task_id, project_id, TASK_SCHEMA, "1.0", title.strip(), parent_task_id, "open", 1, now, now),
            )
            for dependency in depends_on or []:
                self.task(dependency)
                conn.execute("INSERT INTO task_dependencies(task_id,depends_on) VALUES(?,?)", (task_id, dependency))
            self._bump_project(conn)
        return self.task(task_id)

    def set_default(self, task_id: str) -> dict[str, Any]:
        self.task(task_id)
        with self.transaction() as conn:
            conn.execute("UPDATE projects SET default_task_id=?,state_version=state_version+1,updated_at=?", (task_id, utc_now()))
        return self.project()

    def begin_task(
        self,
        title: str,
        contract: dict[str, Any],
        *,
        plan: str,
        input_snapshot: dict[str, Any] | None = None,
        actor: str = "codex",
        context_id: str | None = None,
        host_context: dict[str, Any] | None = None,
        parent_task_id: str | None = None,
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        task = self.create_task(title, parent_task_id=parent_task_id, depends_on=depends_on)
        locked = self.lock_contract(task["task_id"], contract, expected_version=1)
        self.set_default(task["task_id"])
        attempt = self.start_attempt(
            task["task_id"],
            expected_version=2,
            plan=plan,
            input_snapshot=input_snapshot or {},
            actor=actor,
            context_id=context_id,
            host_context=host_context,
        )
        return {
            "task": self.task(task["task_id"]),
            "contract": locked,
            "attempt": attempt,
            "recovery": self.recovery(task["task_id"]),
        }

    def lock_contract(self, task_id: str, content: dict[str, Any], *, expected_version: int, revision_reason: str = "") -> dict[str, Any]:
        task = self.task(task_id)
        if task["lifecycle_status"] != "open":
            raise InvalidTransitionError("only open Tasks may lock a ContractRevision")
        if int(task["state_version"]) != expected_version:
            raise ConflictError("Task state_version is stale")
        if task.get("active_attempt_id"):
            raise InvalidTransitionError("abort or seal the active Attempt before replacing its ContractRevision")
        normalized = normalize_contract(self.workspace, content)
        errors = validate_contract(normalized)
        if errors:
            raise ValueError("; ".join(errors))
        if task.get("contract_head_id") and not revision_reason:
            raise ValueError("revision_reason is required to replace a ContractRevision")
        if task.get("contract_head_id"):
            self._assert_assurance_revision(task, normalized)
        revision_row = self.conn.execute("SELECT COALESCE(MAX(revision),0) FROM contracts WHERE task_id=?", (task_id,)).fetchone()
        revision = int(revision_row[0]) + 1
        contract_id = new_id("contract")
        parent = task.get("contract_head_id")
        now = utc_now()
        content = dict(normalized)
        content["revision_reason"] = revision_reason
        digest = contract_hash(content)
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO contracts(contract_id,task_id,revision,parent_contract_id,schema,content_json,content_hash,locked_at) VALUES(?,?,?,?,?,?,?,?)",
                (contract_id, task_id, revision, parent, content["schema"], _json(content), digest, now),
            )
            cursor = conn.execute("UPDATE tasks SET contract_head_id=?,acceptance_head_id=NULL,state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=?", (contract_id, now, task_id, expected_version))
            if cursor.rowcount != 1:
                raise ConflictError("Task changed while locking ContractRevision")
            self._bump_project(conn)
        return self.contract(task_id)

    def contract(self, task_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT c.* FROM contracts c JOIN tasks t ON t.contract_head_id=c.contract_id WHERE t.task_id=?", (task_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"ContractRevision not found for Task: {task_id}")
        value = dict(row)
        value["content"] = json.loads(value.pop("content_json"))
        if contract_hash(value["content"]) != value["content_hash"]:
            raise DurableError(f"ContractRevision content hash mismatch: {value['contract_id']}")
        return value

    def assurance_state(self, task_id: str) -> dict[str, Any]:
        rows = self.conn.execute("SELECT content_json FROM contracts WHERE task_id=? ORDER BY revision", (task_id,)).fetchall()
        if not rows:
            return {
                "declared_tier": None,
                "effective_tier": None,
                "sticky_tier": None,
                "trigger_ids": [],
                "unresolved_trigger_ids": [],
                "resolved_trigger_proofs": {},
                "required_authorities": [],
                "legacy": False,
            }
        unresolved: set[str] = set()
        resolved_proofs: dict[str, list[str]] = {}
        current = contract_assurance(json.loads(rows[-1][0]))
        for row in rows:
            assurance = contract_assurance(json.loads(row[0]))
            resolution_id = assurance.get("resolution_evaluation_id")
            if resolution_id:
                try:
                    chain = self._evaluation_chain(self.evaluation(str(resolution_id)))
                    if all(item["decision"] == "approved" for item in chain):
                        proofs = self.resolved_trigger_proofs(chain)
                        for trigger_id in assurance["resolved_trigger_ids"]:
                            if trigger_id in proofs:
                                unresolved.discard(trigger_id)
                                resolved_proofs[trigger_id] = proofs[trigger_id]
                except DurableError:
                    pass
            if assurance["tier"] == "high_assurance":
                unresolved.update(assurance["trigger_ids"])
        declared = current["tier"]
        declared_level = ASSURANCE_LEVELS.get(declared, 1)
        sticky_level = 3 if unresolved else declared_level
        effective_level = max(declared_level, sticky_level)
        effective = _tier_name(effective_level)
        authorities = set(current["required_authorities"])
        if effective == "high_assurance":
            authorities.add("reviewer")
        return {
            "declared_tier": declared,
            "effective_tier": effective,
            "sticky_tier": "high_assurance" if unresolved else None,
            "trigger_ids": current["trigger_ids"],
            "unresolved_trigger_ids": sorted(unresolved),
            "resolved_trigger_proofs": resolved_proofs,
            "required_authorities": sorted(authorities),
            "legacy": declared == "legacy",
        }

    def control_projection(self, task_id: str) -> dict[str, Any]:
        task = self.task(task_id)
        assurance = self.assurance_state(task_id)
        if task["lifecycle_status"] == "completed":
            return _projection("accepted", assurance=assurance, next_transition="none", next_action="none")
        if task["lifecycle_status"] != "open":
            return _projection(
                task["lifecycle_status"],
                assurance=assurance,
                next_transition="none",
                next_action="transition the Task to open before continuing" if task["lifecycle_status"] == "paused" else "none",
                blocker=f"Task lifecycle is {task['lifecycle_status']}",
            )
        if not task.get("contract_head_id"):
            return _projection("design_required", assurance=assurance, next_transition="none", next_action="lock a ContractRevision")
        if task.get("active_attempt_id"):
            return _projection("working", assurance=assurance, next_transition="none", next_action="continue the active Attempt")
        head_id = task.get("acceptance_head_id")
        if not head_id:
            latest = self.latest_attempt(task_id)
            if latest and latest["status"] == "sealed" and latest["contract_id"] == task.get("contract_head_id"):
                existing = self.conn.execute("SELECT 1 FROM evaluations WHERE task_id=? AND subject_type='attempt' AND subject_id=? AND kind='verification' LIMIT 1", (task_id, latest["attempt_id"])).fetchone()
                if existing:
                    return _projection("evaluation_chain_invalid", assurance=assurance, next_transition="start_repair_attempt", next_action="start a repair Attempt", blocker="latest sealed Attempt has an orphaned verification Evaluation")
                return _projection("mechanically_ready", assurance=assurance, next_transition="verify", next_action="verify the latest sealed Attempt")
            return _projection("ready", assurance=assurance, next_transition="none", next_action="start an Attempt")
        chain = self._evaluation_chain(self.evaluation(head_id))
        root = chain[0]
        if root["kind"] != "verification" or root["subject_type"] != "attempt":
            return _projection("evaluation_chain_invalid", assurance=assurance, next_transition="start_repair_attempt", next_action="start a repair Attempt", blocker="active Evaluation chain has no verification root")
        attempt = self.attempt(root["subject_id"])
        latest = self.latest_attempt(task_id)
        if attempt["contract_id"] != task.get("contract_head_id") or latest is None or latest["attempt_id"] != attempt["attempt_id"]:
            return _projection("evaluation_chain_invalid", assurance=assurance, next_transition="start_repair_attempt", next_action="start a repair Attempt", blocker="active Evaluation chain does not bind the current Contract and latest Attempt")
        if root["decision"] != "approved":
            return _projection("verification_failed", assurance=assurance, next_transition="start_repair_attempt", next_action="diagnose and start a repair Attempt", blocker="mechanical verification was rejected")
        reviews = chain[1:]
        if any(item["decision"] != "approved" for item in reviews):
            return _projection("review_needs_changes", assurance=assurance, next_transition="start_repair_attempt", next_action="diagnose and start a repair Attempt", blocker="a Review rejected the current Attempt or requested changes")
        sequence = _evaluation_authority_sequence(root)
        if sequence is None:
            return _projection("evaluation_chain_invalid", assurance=assurance, next_transition="start_repair_attempt", next_action="start a repair Attempt", blocker="verification contains an invalid authority plan")
        actual = [item["authority"] for item in reviews]
        if (
            any(item["kind"] != "review" or item["payload"].get("authority", item["authority"]) != item["authority"] for item in reviews)
            or actual != sequence[: len(actual)]
            or len(actual) > len(sequence)
        ):
            return _projection("evaluation_chain_invalid", assurance=assurance, authority_sequence=sequence, next_transition="start_repair_attempt", next_action="start a repair Attempt", blocker="historical Review authorities are out of order, duplicated, or extra")
        if not set(assurance["required_authorities"]).issubset(sequence):
            return _projection("evaluation_chain_invalid", assurance=assurance, authority_sequence=sequence, next_transition="start_repair_attempt", next_action="start a repair Attempt", blocker="verification authority plan omits current assurance requirements")
        pending = sequence[len(actual) :]
        proofs = self.resolved_trigger_proofs(chain)
        reviewer_reviews = [item for item in reviews if item["authority"] == "reviewer"]
        if assurance["effective_tier"] == "high_assurance" and reviewer_reviews and not all(
            self._review_has_verified_independence(item, attempt) and item["payload"].get("review_report")
            for item in reviewer_reviews
        ):
            return _projection(
                "high_assurance_review_unverified",
                assurance=assurance,
                authority_sequence=sequence,
                resolved_trigger_proofs=proofs,
                next_transition="start_repair_attempt",
                next_action="start a repair Attempt and obtain a host-attested fresh-context Review",
                blocker="the Tier 3 reviewer context is not host-verified and independent",
            )
        if pending:
            authority = pending[0]
            status = "mechanically_verified_pending_reviewer" if authority == "reviewer" else "reviewed_ready_for_user_acceptance"
            action = "run a fresh-context Review" if authority == "reviewer" else "request the reserved user decision"
            return _projection(status, assurance=assurance, authority_sequence=sequence, pending_authorities=pending, resolved_trigger_proofs=proofs, next_transition=f"review:{authority}", next_action=action)
        return _projection("acceptance_ready", assurance=assurance, authority_sequence=sequence, resolved_trigger_proofs=proofs, next_transition="accept", next_action="accept the active Evaluation head")

    def acceptance_status(self, task_id: str) -> dict[str, Any]:
        return self.control_projection(task_id)

    def resolved_trigger_proofs(self, chain: list[dict[str, Any]]) -> dict[str, list[str]]:
        if not chain or chain[0]["kind"] != "verification" or chain[0]["decision"] != "approved":
            return {}
        proofs: dict[str, set[str]] = {}
        root = chain[0]
        for result in root["payload"].get("validator_results", []):
            if not isinstance(result, dict) or result.get("passed") is not True:
                continue
            validator_id = result.get("validator_id")
            trigger_ids = result.get("resolves_trigger_ids", [])
            if not isinstance(validator_id, str) or not validator_id or not isinstance(trigger_ids, list):
                continue
            for trigger_id in trigger_ids:
                if isinstance(trigger_id, str) and trigger_id:
                    proofs.setdefault(trigger_id, set()).add(f"validator:{validator_id}")
        try:
            attempt = self.attempt(root["subject_id"])
        except DurableError:
            attempt = None
        for review in chain[1:]:
            report = review["payload"].get("review_report")
            if (
                attempt is None
                or review["kind"] != "review"
                or review["authority"] != "reviewer"
                or review["decision"] != "approved"
                or not isinstance(report, dict)
                or not self._review_has_verified_independence(review, attempt)
            ):
                continue
            for trigger_id in report.get("resolved_trigger_ids", []):
                if isinstance(trigger_id, str) and trigger_id:
                    proofs.setdefault(trigger_id, set()).add(f"evaluation:{review['evaluation_id']}")
        return {trigger_id: sorted(items) for trigger_id, items in sorted(proofs.items())}

    def depend(self, task_id: str, dependency: str, *, expected_version: int) -> dict[str, Any]:
        task = self.task(task_id)
        self.task(dependency)
        if task["state_version"] != expected_version:
            raise ConflictError("Task state_version is stale")
        if task["lifecycle_status"] != "open":
            raise InvalidTransitionError("only open Tasks may change dependencies")
        if task_id == dependency:
            raise ValueError("Task cannot depend on itself")
        if self._would_cycle(task_id, dependency):
            raise ValueError("dependency would create a cycle")
        with self.transaction() as conn:
            conn.execute("INSERT INTO task_dependencies(task_id,depends_on) VALUES(?,?)", (task_id, dependency))
            cursor = conn.execute("UPDATE tasks SET state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=?", (utc_now(), task_id, expected_version))
            if cursor.rowcount != 1:
                raise ConflictError("Task changed while adding dependency")
            self._bump_project(conn)
        return self.task(task_id)

    def transition(self, task_id: str, state: str, *, expected_version: int) -> dict[str, Any]:
        if state not in TASK_STATES:
            raise ValueError(f"invalid Task state: {state}")
        task = self.task(task_id)
        if task["state_version"] != expected_version:
            raise ConflictError("Task state_version is stale")
        if state == "completed":
            raise InvalidTransitionError("Task completion requires evaluate accept")
        with self.transaction() as conn:
            cursor = conn.execute("UPDATE tasks SET lifecycle_status=?,state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=?", (state, utc_now(), task_id, expected_version))
            if cursor.rowcount != 1:
                raise ConflictError("Task changed during lifecycle transition")
            self._bump_project(conn)
        return self.task(task_id)

    def start_attempt(
        self,
        task_id: str,
        *,
        expected_version: int,
        plan: str,
        input_snapshot: dict[str, Any],
        actor: str = "codex",
        context_id: str | None = None,
        host_context: dict[str, Any] | None = None,
        retry_of: str | None = None,
        retry_reason: str = "",
    ) -> dict[str, Any]:
        task = self.task(task_id)
        if task["state_version"] != expected_version:
            raise ConflictError("Task state_version is stale")
        if task["lifecycle_status"] != "open":
            raise InvalidTransitionError("Task is not open")
        if not task.get("contract_head_id"):
            raise InvalidTransitionError("Task has no locked ContractRevision")
        projection = self.control_projection(task_id)
        if projection["next_transition"] not in {"none", "start_repair_attempt"}:
            raise InvalidTransitionError(f"Task control state requires {projection['next_transition']}")
        if task.get("active_attempt_id"):
            raise InvalidTransitionError("Task already has an active Attempt")
        unresolved = [dep for dep in task["depends_on"] if self.task(dep)["lifecycle_status"] != "completed"]
        if unresolved:
            raise InvalidTransitionError(f"Task dependencies are incomplete: {', '.join(unresolved)}")
        if self.conn.execute("SELECT 1 FROM attempts a JOIN tasks t ON t.task_id=a.task_id WHERE t.project_id=? AND a.status='open' LIMIT 1", (self.project_id(),)).fetchone():
            raise ConflictError("the Project worktree already has an open mutating Attempt")
        contract = self.contract(task_id)
        stable_errors = verify_stable_inputs(self.workspace, contract["content"])
        if stable_errors:
            raise DurableError("; ".join(stable_errors))
        if self.recovery(task_id)["status"] != "fresh":
            raise InvalidTransitionError("RecoveryView must be fresh before Attempt start")
        stamp = GitWorkspace(self.workspace).stamp()
        if stamp.unknown_reason:
            raise DurableError(f"workspace state unknown: {stamp.unknown_reason}")
        plan_hash = _digest(plan)
        input_hash = _digest(input_snapshot)
        fingerprint = _digest({"contract": contract["content_hash"], "plan": plan_hash, "input": input_hash})
        duplicate = self.conn.execute("SELECT attempt_id FROM attempts WHERE task_id=? AND fingerprint=? AND status IN ('sealed','aborted')", (task_id, fingerprint)).fetchone()
        if duplicate and not retry_reason.strip():
            raise DuplicateAttemptError("exact Attempt replay requires retry_reason")
        attempt_id = new_id("attempt")
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO attempts(attempt_id,task_id,contract_id,schema,status,plan,plan_hash,input_json,input_hash,fingerprint,baseline_stamp_json,baseline_stamp_hash,started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (attempt_id, task_id, contract["contract_id"], ATTEMPT_SCHEMA, "open", plan, plan_hash, _json(input_snapshot), input_hash, fingerprint, _json(stamp.to_dict()), stamp.content_hash(), now),
            )
            self._append_record(conn, attempt_id, "attempt_started", {"actor": actor, "context": _context_provenance(context_id, host_context), "plan": plan, "retry_of": retry_of, "retry_reason": retry_reason, "baseline_stamp": stamp.to_dict()})
            if task.get("acceptance_head_id") is None:
                cursor = conn.execute(
                    "UPDATE tasks SET active_attempt_id=?,acceptance_head_id=NULL,state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=? AND acceptance_head_id IS NULL",
                    (attempt_id, now, task_id, expected_version),
                )
            else:
                cursor = conn.execute(
                    "UPDATE tasks SET active_attempt_id=?,acceptance_head_id=NULL,state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=? AND acceptance_head_id=?",
                    (attempt_id, now, task_id, expected_version, task["acceptance_head_id"]),
                )
            if cursor.rowcount != 1:
                raise ConflictError("Task or active Evaluation head changed while starting Attempt")
            self._bump_project(conn)
        return self.attempt(attempt_id)

    def record_checkpoint(self, attempt_id: str, payload: dict[str, Any], *, expected_version: int) -> dict[str, Any]:
        attempt = self.attempt(attempt_id)
        task = self.task(attempt["task_id"])
        if task["state_version"] != expected_version:
            raise ConflictError("Task state_version is stale")
        if attempt["status"] != "open":
            raise InvalidTransitionError("only open Attempts accept checkpoints")
        contract = self.contract(attempt["task_id"])["content"]
        stable_errors = verify_stable_inputs(self.workspace, contract)
        if stable_errors:
            raise DurableError("; ".join(stable_errors))
        current = GitWorkspace(self.workspace).stamp()
        if current.unknown_reason:
            raise DurableError(f"workspace state unknown: {current.unknown_reason}")
        previous_payload = self._latest_checkpoint_payload(attempt_id)
        previous = WorkspaceStamp.from_dict(previous_payload["workspace_stamp"]) if previous_payload and previous_payload.get("workspace_stamp") else WorkspaceStamp.from_dict(attempt["baseline_stamp"])
        if previous.head_oid != current.head_oid and compare_stamps(previous, current) != "aligned":
            raise ConflictError("HEAD changed since the latest checkpoint; resolve the branch/reset conflict explicitly")
        delta = changed_paths_between(previous, current)
        claimed = set(str(item) for item in payload.get("claimed_paths", []))
        deferred = _path_set(payload.get("deferred_paths", []))
        assigned = _path_set(payload.get("assigned_paths", []))
        if claimed & deferred or claimed & assigned or deferred & assigned:
            raise ValueError("checkpoint path classifications must be mutually exclusive")
        for item in payload.get("deferred_paths", []):
            if not isinstance(item, dict) or not str(item.get("reason") or "").strip():
                raise ValueError("deferred paths require a reason")
        for item in payload.get("assigned_paths", []):
            if not isinstance(item, dict) or not item.get("task_id"):
                raise ValueError("assigned paths require a task_id")
            self.task(str(item["task_id"]))
        decision = str(payload.get("decision") or "")
        if decision and decision not in DECISIONS:
            raise ValueError("checkpoint decision must be explicit and valid")
        evidence_ids = {item["evidence_id"] for item in attempt["evidence"]}
        missing_evidence = sorted(set(payload.get("evidence_refs", [])) - evidence_ids)
        if missing_evidence:
            raise ValueError("checkpoint evidence_refs do not belong to this Attempt: " + ", ".join(missing_evidence))
        classified = claimed | deferred | assigned
        missing = sorted(set(delta) - classified)
        unknown = sorted(classified - set(delta))
        if missing:
            raise ConflictError("workspace ahead; classify changed paths before checkpoint: " + ", ".join(missing))
        if unknown:
            raise ValueError("checkpoint classifications must refer to changed paths: " + ", ".join(unknown))
        if any(path in claimed and not path_allowed(path, contract.get("execution_scope", {}).get("paths", [])) for path in delta):
            raise ConflictError("claimed path falls outside execution_scope.paths")
        payload = dict(payload)
        payload["schema"] = CHECKPOINT_SCHEMA
        payload["workspace_stamp"] = current.to_dict()
        payload["workspace_alignment"] = "aligned"
        with self.transaction() as conn:
            record = self._append_record(conn, attempt_id, "checkpoint", payload)
            conn.execute("UPDATE attempts SET latest_checkpoint_hash=? WHERE attempt_id=?", (record["content_hash"], attempt_id))
            cursor = conn.execute("UPDATE tasks SET state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=?", (utc_now(), attempt["task_id"], expected_version))
            if cursor.rowcount != 1:
                raise ConflictError("Task changed while recording checkpoint")
            self._bump_project(conn)
        return record

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        checkpoint_payload: dict[str, Any] | None = None,
        evidence_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        attempt = self.attempt(attempt_id)
        if attempt["status"] != "open":
            raise InvalidTransitionError("attempt finish requires an open Attempt")
        task = self.task(attempt["task_id"])
        contract = self.contract(task["task_id"])["content"]
        current = GitWorkspace(self.workspace).stamp()
        previous_payload = self._latest_checkpoint_payload(attempt_id)
        previous = (
            WorkspaceStamp.from_dict(previous_payload["workspace_stamp"])
            if previous_payload and previous_payload.get("workspace_stamp")
            else WorkspaceStamp.from_dict(attempt["baseline_stamp"])
        )
        delta = changed_paths_between(previous, current)
        payload = dict(checkpoint_payload or {})
        declared_outputs = set(managed_output_paths(contract))
        claimed = set(str(item) for item in payload.get("claimed_paths", []))
        claimed.update(path for path in delta if path in declared_outputs)
        payload.setdefault("completed", [])
        payload.setdefault("observations", [])
        payload.setdefault("diagnosis", "")
        payload.setdefault("decision", "complete")
        payload.setdefault("next_plan", "verify and accept the exact Attempt")
        payload["claimed_paths"] = sorted(claimed)
        payload.setdefault("deferred_paths", [])
        payload.setdefault("assigned_paths", [])
        payload.setdefault("evidence_refs", [])
        checkpoint = self.record_checkpoint(attempt_id, payload, expected_version=task["state_version"])

        bound_evidence = {item["path"]: item for item in self.evidence(attempt_id)}
        evidence = []
        for path in sorted(declared_outputs | set(evidence_paths or [])):
            item = bound_evidence.get(path) or self.add_evidence(attempt_id, path)
            evidence.append(item)

        task = self.task(task["task_id"])
        sealed = self.seal_attempt(attempt_id, expected_version=task["state_version"])
        evaluation = self.evaluate_verify(attempt_id)
        pending = list(evaluation["payload"].get("required_authorities", []))
        accepted = None
        if evaluation["decision"] == "approved" and not pending:
            task = self.task(task["task_id"])
            accepted = self.accept(task["task_id"], evaluation["evaluation_id"], expected_version=task["state_version"])
        return {
            "checkpoint": checkpoint,
            "evidence": evidence,
            "attempt": sealed,
            "evaluation": evaluation,
            "task": accepted or self.task(task["task_id"]),
            "pending_authorities": pending,
        }

    def add_evidence(self, attempt_id: str, path: str, *, description: str = "") -> dict[str, Any]:
        attempt = self.attempt(attempt_id)
        if attempt["status"] != "open":
            raise InvalidTransitionError("Evidence can only be added to an open Attempt")
        file_path = self._safe_file(path)
        evidence = {"evidence_id": new_id("evidence"), "attempt_id": attempt_id, "path": Path(path).as_posix(), "sha256": _file_hash(file_path), "media_type": "application/octet-stream", "description": description, "created_at": utc_now()}
        with self.transaction() as conn:
            conn.execute("INSERT INTO evidence(evidence_id,attempt_id,path,sha256,media_type,description,created_at) VALUES(?,?,?,?,?,?,?)", tuple(evidence.values()))
            self._bump_project(conn)
        return evidence

    def seal_attempt(self, attempt_id: str, *, expected_version: int) -> dict[str, Any]:
        attempt = self.attempt(attempt_id)
        task = self.task(attempt["task_id"])
        if task["state_version"] != expected_version:
            raise ConflictError("Task state_version is stale")
        if attempt["status"] != "open":
            raise InvalidTransitionError("Attempt is not open")
        contract = self.contract(task["task_id"])["content"]
        self._assert_aligned(attempt, contract)
        evidence = self.evidence(attempt_id)
        by_path = {item["path"]: item for item in evidence}
        for path in managed_output_paths(contract):
            if path not in by_path:
                raise DurableError(f"managed output evidence is required before seal: {path}")
        for item in evidence:
            live_hash = _file_hash(self._safe_file(item["path"]))
            if live_hash != item["sha256"]:
                raise DurableError(f"evidence hash drift: {item['path']}")
        manifest = {"attempt_id": attempt_id, "contract_id": attempt["contract_id"], "evidence": evidence, "records": self.records(attempt_id), "outcome": "sealed"}
        execution_hash = _digest(manifest)
        now = utc_now()
        with self.transaction() as conn:
            attempt_cursor = conn.execute("UPDATE attempts SET status='sealed',sealed_at=?,execution_hash=? WHERE attempt_id=? AND status='open'", (now, execution_hash, attempt_id))
            task_cursor = conn.execute("UPDATE tasks SET active_attempt_id=NULL,state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=? AND active_attempt_id=?", (now, task["task_id"], expected_version, attempt_id))
            if attempt_cursor.rowcount != 1 or task_cursor.rowcount != 1:
                raise ConflictError("Task or Attempt changed while sealing")
            self._bump_project(conn)
        return self.attempt(attempt_id)

    def abort_attempt(self, attempt_id: str, *, reason: str) -> dict[str, Any]:
        attempt = self.attempt(attempt_id)
        if attempt["status"] != "open":
            raise InvalidTransitionError("Attempt is not open")
        with self.transaction() as conn:
            conn.execute("UPDATE attempts SET status='aborted',sealed_at=? WHERE attempt_id=?", (utc_now(), attempt_id))
            conn.execute("UPDATE tasks SET active_attempt_id=NULL,state_version=state_version+1,updated_at=? WHERE task_id=?", (utc_now(), attempt["task_id"]))
            self._append_record(conn, attempt_id, "aborted", {"reason": reason})
            self._bump_project(conn)
        return self.attempt(attempt_id)

    def evaluate_verify(self, attempt_id: str) -> dict[str, Any]:
        attempt = self.attempt(attempt_id)
        if attempt["status"] != "sealed":
            raise InvalidTransitionError("only sealed Attempts may be verified")
        task = self.task(attempt["task_id"])
        if task["lifecycle_status"] != "open":
            raise InvalidTransitionError("only open Tasks may create Evaluations")
        contract_record = self.contract(task["task_id"])
        if attempt["contract_id"] != contract_record["contract_id"]:
            raise ConflictError("Attempt belongs to a superseded ContractRevision")
        latest = self.latest_attempt(task["task_id"])
        if latest is None or latest["attempt_id"] != attempt_id:
            raise ConflictError("verification requires the current Contract's latest sealed Attempt")
        duplicate = self.conn.execute("SELECT evaluation_id FROM evaluations WHERE subject_type='attempt' AND subject_id=? AND kind='verification' LIMIT 1", (attempt_id,)).fetchone()
        if duplicate:
            raise InvalidTransitionError(f"Attempt already has a verification Evaluation: {duplicate[0]}")
        projection = self.control_projection(task["task_id"])
        if projection["next_transition"] != "verify":
            raise InvalidTransitionError(f"Task control state requires {projection['next_transition']}")
        contract = contract_record["content"]
        self._assert_aligned(attempt, contract)
        before = GitWorkspace(self.workspace).stamp()
        results: list[dict[str, Any]] = []
        assurance = self.assurance_state(task["task_id"])
        required_authorities: list[str] = list(assurance["required_authorities"])
        for validator in contract.get("verification_spec", {}).get("validators", []):
            if validator.get("mode") == "manual":
                required_authorities.append("user" if validator.get("authority") == "user" or validator.get("requires_user_confirmation") else "reviewer")
            else:
                results.append(self._run_validator(validator))
        for gate in contract.get("verification_spec", {}).get("resource_gates", []):
            required_authorities.append("user" if gate.get("requires_user_confirmation") else "reviewer")
        after = GitWorkspace(self.workspace).stamp()
        if compare_stamps(before, after) != "aligned":
            raise DurableError("verification changed or lost workspace alignment; fail closed")
        approved = all(item.get("passed") is True for item in results)
        authority_sequence = _ordered_authorities(required_authorities)
        payload = {
            "validator_results": results,
            "workspace_stamp": after.to_dict(),
            "required_authorities": sorted(set(required_authorities)),
            "authority_sequence": authority_sequence,
            "assurance": assurance,
            "supersedes_evaluation_id": task.get("acceptance_head_id"),
        }
        return self._insert_evaluation(
            task["task_id"],
            "attempt",
            attempt_id,
            attempt["execution_hash"] or "",
            "verification",
            "kernel",
            "metaloop",
            PROTOCOL_VERSION,
            "approved" if approved else "rejected",
            payload,
            activate=True,
            expected_head_id=task.get("acceptance_head_id"),
            expected_task_version=task["state_version"],
        )

    def review(
        self,
        evaluation_id: str,
        *,
        decision: str,
        reviewer: str,
        authority: str = "reviewer",
        report: dict[str, Any] | None = None,
        context_id: str | None = None,
        host_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if decision not in EVALUATION_DECISIONS:
            raise ValueError("invalid review decision")
        if authority not in {"reviewer", "user"}:
            raise ValueError("review authority must be reviewer or user")
        evaluation = self.evaluation(evaluation_id)
        task = self.task(evaluation["task_id"])
        if task["lifecycle_status"] != "open":
            raise InvalidTransitionError("only open Tasks may create Reviews")
        if task.get("acceptance_head_id") != evaluation_id:
            raise ConflictError("Review must extend the Task's active Evaluation head")
        projection = self.control_projection(task["task_id"])
        expected_transition = f"review:{authority}"
        if projection["next_transition"] != expected_transition:
            raise InvalidTransitionError(f"Task control state requires {projection['next_transition']}")
        chain = self._evaluation_chain(evaluation)
        root = chain[0]
        if root["kind"] != "verification" or root["decision"] != "approved":
            raise InvalidTransitionError("Review requires an approved mechanical verification")
        attempt = self.attempt(root["subject_id"])
        contract_record = self.contract(attempt["task_id"])
        if attempt["contract_id"] != contract_record["contract_id"]:
            raise ConflictError("Review target belongs to a superseded ContractRevision")
        self._assert_aligned(attempt, contract_record["content"])
        assurance = self.assurance_state(attempt["task_id"])
        worker = attempt["records"][0]["payload"]
        worker_context = worker.get("context") or _unavailable_context()
        reviewer_context = _context_provenance(context_id, host_context)
        independent = _contexts_are_verified_and_distinct(worker_context, reviewer_context)
        if authority == "reviewer" and assurance["effective_tier"] == "high_assurance":
            if report is None:
                raise ValueError("high_assurance Review requires a structured report")
            if _is_verified_host_context(worker_context) and _is_verified_host_context(reviewer_context) and not independent:
                raise ConflictError("high_assurance Review requires a distinct host context identity")
        elif authority == "reviewer" and not independent and str(worker.get("actor") or "") == reviewer:
            raise ConflictError("reviewer must use a distinct identity or execution context")
        normalized_report = _normalize_review_report(report, decision=decision, evaluation=evaluation, attempt=attempt, contract=contract_record) if report is not None else None
        payload = {
            "reviewer": reviewer,
            "authority": authority,
            "decision": decision,
            "context": reviewer_context,
            "independence": "verified" if independent else "unverified",
            "review_report": normalized_report,
        }
        return self._insert_evaluation(
            evaluation["task_id"],
            "evaluation",
            evaluation_id,
            evaluation["content_hash"],
            "review",
            authority,
            reviewer,
            PROTOCOL_VERSION,
            decision,
            payload,
            activate=True,
            expected_head_id=evaluation_id,
            expected_task_version=task["state_version"],
        )

    def accept(self, task_id: str, evaluation_id: str, *, expected_version: int) -> dict[str, Any]:
        task = self.task(task_id)
        if task["state_version"] != expected_version:
            raise ConflictError("Task state_version is stale")
        if task["lifecycle_status"] != "open":
            raise InvalidTransitionError("only open Tasks may be accepted")
        evaluation = self.evaluation(evaluation_id)
        if evaluation["task_id"] != task_id:
            raise InvalidTransitionError("Evaluation belongs to another Task")
        if task.get("acceptance_head_id") != evaluation_id:
            raise ConflictError("accept requires the Task's active Evaluation head")
        projection = self.control_projection(task_id)
        if projection["next_transition"] != "accept":
            raise InvalidTransitionError(f"Task control state requires {projection['next_transition']}")
        chain = self._evaluation_chain(evaluation)
        root = chain[0]
        if root["kind"] != "verification" or root["decision"] != "approved":
            raise InvalidTransitionError("accept requires an approved verification Evaluation")
        sequence = _evaluation_authority_sequence(root)
        actual = [item["authority"] for item in chain[1:]]
        if any(item["decision"] != "approved" for item in chain[1:]) or sequence is None or actual != sequence:
            raise InvalidTransitionError("acceptance chain does not match the ordered authority plan")
        attempt = self.attempt(root["subject_id"])
        if attempt["status"] != "sealed" or root["subject_hash"] != attempt["execution_hash"]:
            raise ConflictError("Evaluation does not bind the sealed Attempt")
        contract_record = self.contract(task_id)
        if attempt["contract_id"] != contract_record["contract_id"]:
            raise ConflictError("Evaluation belongs to a superseded ContractRevision")
        latest = self.latest_attempt(task_id)
        if latest is None or latest["attempt_id"] != attempt["attempt_id"]:
            raise ConflictError("Evaluation does not bind the latest Attempt")
        assurance = self.assurance_state(task_id)
        if assurance["effective_tier"] == "high_assurance":
            reviewer_reviews = [item for item in chain[1:] if item["authority"] == "reviewer"]
            if not any(self._review_has_verified_independence(item, attempt) and item["payload"].get("review_report") for item in reviewer_reviews):
                raise InvalidTransitionError("high_assurance acceptance requires a structured fresh-context Review")
        self._assert_aligned(attempt, contract_record["content"])
        with self.transaction() as conn:
            cursor = conn.execute("UPDATE tasks SET acceptance_head_id=?,lifecycle_status='completed',state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=? AND acceptance_head_id=?", (evaluation_id, utc_now(), task_id, expected_version, evaluation_id))
            if cursor.rowcount != 1:
                raise ConflictError("Task or active Evaluation head changed while accepting")
            self._bump_project(conn)
        return self.task(task_id)

    def add_decision(self, task_id: str | None, *, scope: str, type: str, summary: str, diagnosis: str = "", decision: str = "", next_plan: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if scope not in {"task", "project"}:
            raise ValueError("decision scope must be task or project")
        if scope == "task" and not task_id:
            raise ValueError("task decision requires task_id")
        if task_id:
            self.task(task_id)
        if type not in DECISION_TYPES:
            raise ValueError("invalid decision event type")
        if decision and decision not in DECISIONS:
            raise ValueError("invalid explicit decision")
        event = {"event_id": new_id("event"), "project_id": self.project_id(), "task_id": task_id if scope == "task" else None, "scope": scope, "type": type, "summary": summary, "diagnosis": diagnosis, "decision": decision, "next_plan": next_plan, "payload": payload or {}, "created_at": utc_now()}
        event["content_hash"] = _digest(event)
        with self.transaction() as conn:
            conn.execute("INSERT INTO decision_events(event_id,project_id,task_id,scope,type,summary,diagnosis,decision,next_plan,payload_json,content_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (event["event_id"], event["project_id"], event["task_id"], scope, type, summary, diagnosis, decision, next_plan, _json(event["payload"]), event["content_hash"], event["created_at"]))
            self._bump_project(conn)
        return event

    def assign_thread(self, thread_id: str, task_id: str, *, role: str = "worker") -> dict[str, Any]:
        self.task(task_id)
        now = utc_now()
        with self.transaction() as conn:
            conn.execute("INSERT INTO thread_assignments(thread_id,task_id,role,assigned_at) VALUES(?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET task_id=excluded.task_id,role=excluded.role,assigned_at=excluded.assigned_at", (thread_id, task_id, role, now))
            self._bump_project(conn)
        return dict(self.conn.execute("SELECT * FROM thread_assignments WHERE thread_id=?", (thread_id,)).fetchone())

    def return_thread(self, thread_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM thread_assignments WHERE thread_id=?", (thread_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"thread assignment not found: {thread_id}")
        with self.transaction() as conn:
            conn.execute("DELETE FROM thread_assignments WHERE thread_id=?", (thread_id,))
            self._bump_project(conn)
        return {"thread_id": thread_id, "returned_from_task": row["task_id"]}

    def assignments(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM thread_assignments ORDER BY assigned_at")]

    def write_recovery(self, task_id: str, markdown: str) -> dict[str, Any]:
        view = self.recovery(task_id)
        now = utc_now()
        with self.transaction() as conn:
            conn.execute("INSERT INTO recovery_views(task_id,schema,source_hash,workspace_alignment,resume_markdown,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET source_hash=excluded.source_hash,workspace_alignment=excluded.workspace_alignment,resume_markdown=excluded.resume_markdown,updated_at=excluded.updated_at", (task_id, RECOVERY_SCHEMA, view["source_hash"], view["workspace_alignment"], markdown, now))
        return self.recovery(task_id)

    def recovery(self, task_id: str) -> dict[str, Any]:
        task = self.task(task_id)
        current = GitWorkspace(self.workspace).stamp()
        attempt = self.latest_attempt(task_id)
        previous = None
        if attempt:
            payload = self._latest_checkpoint_payload(attempt["attempt_id"])
            previous = WorkspaceStamp.from_dict(payload["workspace_stamp"]) if payload and payload.get("workspace_stamp") else WorkspaceStamp.from_dict(attempt["baseline_stamp"])
        alignment = compare_stamps(previous, current)
        transition = alignment_reason(previous, current)
        source = self._recovery_source(task, attempt, current, alignment)
        row = self.conn.execute("SELECT * FROM recovery_views WHERE task_id=?", (task_id,)).fetchone()
        status = "fresh" if alignment == "aligned" else "stale"
        active_head = self.evaluation(task["acceptance_head_id"]) if task.get("acceptance_head_id") else None
        acceptance = self.acceptance_status(task_id)
        next_transition = acceptance["next_transition"]
        next_action = acceptance["next_action"]
        blocker = acceptance["blocker"]
        if alignment != "aligned" and not task.get("active_attempt_id"):
            next_transition = "none"
            next_action = "reconcile workspace state before the next lifecycle transition"
            blocker = f"workspace alignment is {alignment}"
        return {"schema": RECOVERY_SCHEMA, "task_id": task_id, "status": status, "source_hash": source, "workspace_alignment": alignment, "workspace_transition": transition, "workspace_stamp": current.to_dict(), "changed_paths_since_checkpoint": changed_paths_between(previous, current), "resume_markdown": row["resume_markdown"] if row else "", "task": task, "contract": self.contract(task_id) if task.get("contract_head_id") else None, "assurance": self.assurance_state(task_id), "acceptance": acceptance, "next_transition": next_transition, "next_action": next_action, "blocker": blocker, "active_attempt": attempt, "latest_decisions": self.decisions(task_id), "active_evaluation_head": active_head, "acceptance_head_id": task.get("acceptance_head_id")}

    def integrity(self, task_id: str | None = None) -> dict[str, Any]:
        errors: list[str] = []
        project = self.project()
        identity = GitWorkspace(self.workspace).stamp()
        if identity.unknown_reason:
            errors.append("workspace stamp unknown: " + identity.unknown_reason)
        if identity.repository_root != project["repository_root"] or identity.worktree_path != project["worktree_path"]:
            errors.append("Project Git identity drift")
        selected = task_id or project.get("default_task_id")
        if selected:
            try:
                task = self.task(selected)
                if task.get("contract_head_id"):
                    errors.extend(verify_stable_inputs(self.workspace, self.contract(selected)["content"]))
                attempt = self.latest_attempt(selected)
                if attempt:
                    try:
                        self._assert_aligned(attempt, self.contract(selected)["content"])
                    except DurableError as exc:
                        errors.append(str(exc))
                    for item in self.evidence(attempt["attempt_id"]):
                        try:
                            if _file_hash(self._safe_file(item["path"])) != item["sha256"]:
                                errors.append(f"evidence hash drift: {item['path']}")
                        except DurableError as exc:
                            errors.append(str(exc))
                if task.get("acceptance_head_id"):
                    self._evaluation_chain(self.evaluation(task["acceptance_head_id"]))
            except DurableError as exc:
                errors.append(str(exc))
        return {"sqlite": "ok", "passed": not errors, "errors": errors, "workspace_alignment": self.recovery(selected)["workspace_alignment"] if selected else "aligned"}

    def attempt(self, attempt_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Attempt not found: {attempt_id}")
        value = dict(row)
        value["baseline_stamp"] = json.loads(value.pop("baseline_stamp_json"))
        value["input_snapshot"] = json.loads(value.pop("input_json"))
        value["records"] = self.records(attempt_id)
        value["evidence"] = self.evidence(attempt_id)
        started = value["records"][0]["payload"] if value["records"] else {}
        value["worker_context"] = started.get("context") or _unavailable_context()
        return value

    def latest_attempt(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT attempt_id FROM attempts WHERE task_id=? ORDER BY started_at DESC LIMIT 1", (task_id,)).fetchone()
        return self.attempt(row[0]) if row else None

    def records(self, attempt_id: str) -> list[dict[str, Any]]:
        return [self._record_value(row) for row in self.conn.execute("SELECT * FROM attempt_records WHERE attempt_id=? ORDER BY seq", (attempt_id,))]

    def evidence(self, attempt_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM evidence WHERE attempt_id=? ORDER BY created_at", (attempt_id,))]

    def evaluation(self, evaluation_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (evaluation_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Evaluation not found: {evaluation_id}")
        value = dict(row)
        value["payload"] = json.loads(value.pop("content_json"))
        expected = _digest({key: value[key] for key in ("evaluation_id", "task_id", "subject_type", "subject_id", "subject_hash", "kind", "authority", "evaluator", "evaluator_version", "decision", "payload", "created_at")})
        if expected != value["content_hash"]:
            raise DurableError(f"Evaluation content hash mismatch: {evaluation_id}")
        return value

    def decisions(self, task_id: str | None = None) -> list[dict[str, Any]]:
        if task_id:
            rows = self.conn.execute("SELECT * FROM decision_events WHERE task_id=? OR scope='project' ORDER BY created_at", (task_id,))
        else:
            rows = self.conn.execute("SELECT * FROM decision_events ORDER BY created_at")
        values = []
        for row in rows:
            value = dict(row)
            value["payload"] = json.loads(value.pop("payload_json"))
            values.append(value)
        return values

    def _assert_aligned(self, attempt: dict[str, Any], contract: dict[str, Any]) -> None:
        if attempt["status"] == "sealed":
            manifest = {"attempt_id": attempt["attempt_id"], "contract_id": attempt["contract_id"], "evidence": attempt["evidence"], "records": attempt["records"], "outcome": "sealed"}
            if _digest(manifest) != attempt["execution_hash"]:
                raise DurableError(f"sealed Attempt content hash mismatch: {attempt['attempt_id']}")
        current = GitWorkspace(self.workspace).stamp()
        latest = self._latest_checkpoint_payload(attempt["attempt_id"])
        previous = WorkspaceStamp.from_dict(latest["workspace_stamp"]) if latest and latest.get("workspace_stamp") else WorkspaceStamp.from_dict(attempt["baseline_stamp"])
        alignment = compare_stamps(previous, current)
        if alignment != "aligned":
            raise DurableError(f"workspace alignment is {alignment}; checkpoint/reconcile before continuing")
        stable_errors = verify_stable_inputs(self.workspace, contract)
        if stable_errors:
            raise DurableError("; ".join(stable_errors))
        for item in attempt["evidence"]:
            if _file_hash(self._safe_file(item["path"])) != item["sha256"]:
                raise DurableError(f"evidence hash drift: {item['path']}")

    def _review_has_verified_independence(self, review: dict[str, Any], attempt: dict[str, Any]) -> bool:
        return bool(
            review["payload"].get("independence") == "verified"
            and _contexts_are_verified_and_distinct(
                attempt.get("worker_context") or _unavailable_context(),
                review["payload"].get("context") or _unavailable_context(),
            )
        )

    def _assert_assurance_revision(self, task: dict[str, Any], content: dict[str, Any]) -> None:
        previous = self.assurance_state(task["task_id"])
        proposed = contract_assurance(content)
        if previous["effective_tier"] != "high_assurance" or ASSURANCE_LEVELS.get(proposed["tier"], 1) >= 3:
            return
        unresolved = set(previous["unresolved_trigger_ids"])
        resolved = set(proposed["resolved_trigger_ids"])
        if not unresolved or not unresolved.issubset(resolved):
            missing = sorted(unresolved - resolved)
            raise InvalidTransitionError("Tier 3 remains sticky; resolve every active trigger" + (": " + ", ".join(missing) if missing else ""))
        if not proposed["rationale"]:
            raise ValueError("assurance downgrade requires rationale in the new ContractRevision")
        resolution_id = proposed.get("resolution_evaluation_id")
        if not resolution_id:
            raise InvalidTransitionError("assurance downgrade requires an approved resolution_evaluation_id")
        if task.get("acceptance_head_id") != resolution_id:
            raise ConflictError("assurance resolution must reference the active Evaluation head")
        chain = self._evaluation_chain(self.evaluation(str(resolution_id)))
        if any(item["decision"] != "approved" for item in chain):
            raise InvalidTransitionError("assurance resolution Evaluation chain must be approved")
        root = chain[0]
        if root["kind"] != "verification":
            raise InvalidTransitionError("assurance resolution must derive from mechanical verification")
        attempt = self.attempt(root["subject_id"])
        if attempt["contract_id"] != task["contract_head_id"]:
            raise ConflictError("assurance resolution does not bind the current ContractRevision")
        proofs = self.resolved_trigger_proofs(chain)
        missing_proofs = sorted(unresolved - set(proofs))
        if missing_proofs:
            raise InvalidTransitionError(
                "assurance downgrade lacks normalized proof for triggers: " + ", ".join(missing_proofs)
            )

    def _run_validator(self, validator: dict[str, Any]) -> dict[str, Any]:
        kind = str(validator.get("type") or "")
        proof_binding = {
            "validator_id": validator.get("validator_id"),
            "resolves_trigger_ids": list(validator.get("resolves_trigger_ids", [])),
        }
        if kind == "command":
            command = str(validator.get("command") or "")
            result = subprocess.run(command, shell=True, cwd=self.workspace, text=True, capture_output=True, timeout=int(validator.get("timeout", 600)), check=False)
            return {"type": kind, "command": command, "passed": result.returncode == 0, "exit_code": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:], **proof_binding}
        if kind == "file_exists":
            path = str(validator.get("path") or "")
            return {"type": kind, "path": path, "passed": self._safe_file(path).is_file(), **proof_binding}
        if kind == "artifact_hash":
            path = str(validator.get("path") or "")
            expected = str(validator.get("sha256") or "")
            actual = _file_hash(self._safe_file(path))
            return {"type": kind, "path": path, "expected": expected, "actual": actual, "passed": actual == expected, **proof_binding}
        return {"type": kind, "passed": False, "message": "unsupported validator", **proof_binding}

    def _insert_evaluation(
        self,
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
        *,
        activate: bool = False,
        expected_head_id: str | None = None,
        expected_task_version: int | None = None,
    ) -> dict[str, Any]:
        evaluation_id = new_id("evaluation")
        value = {"evaluation_id": evaluation_id, "task_id": task_id, "subject_type": subject_type, "subject_id": subject_id, "subject_hash": subject_hash, "kind": kind, "authority": authority, "evaluator": evaluator, "evaluator_version": evaluator_version, "decision": decision, "payload": payload, "created_at": utc_now()}
        digest = _digest(value)
        with self.transaction() as conn:
            conn.execute("INSERT INTO evaluations(evaluation_id,task_id,subject_type,subject_id,subject_hash,kind,authority,evaluator,evaluator_version,decision,content_json,content_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (evaluation_id, task_id, subject_type, subject_id, subject_hash, kind, authority, evaluator, evaluator_version, decision, _json(payload), digest, value["created_at"]))
            if activate:
                if expected_task_version is None:
                    raise ValueError("active Evaluation updates require expected_task_version")
                if expected_head_id is None:
                    cursor = conn.execute(
                        "UPDATE tasks SET acceptance_head_id=?,state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=? AND acceptance_head_id IS NULL",
                        (evaluation_id, utc_now(), task_id, expected_task_version),
                    )
                else:
                    cursor = conn.execute(
                        "UPDATE tasks SET acceptance_head_id=?,state_version=state_version+1,updated_at=? WHERE task_id=? AND state_version=? AND acceptance_head_id=?",
                        (evaluation_id, utc_now(), task_id, expected_task_version, expected_head_id),
                    )
                if cursor.rowcount != 1:
                    raise ConflictError("Task state or active Evaluation head changed concurrently")
            self._bump_project(conn)
        value["content_hash"] = digest
        if activate and expected_task_version is not None:
            value["task_state_version"] = expected_task_version + 1
        return value

    def _evaluation_chain(self, head: dict[str, Any]) -> list[dict[str, Any]]:
        chain = [head]
        seen = {head["evaluation_id"]}
        while chain[-1]["subject_type"] == "evaluation":
            parent = self.evaluation(chain[-1]["subject_id"])
            if parent["evaluation_id"] in seen:
                raise DurableError("Evaluation chain cycle")
            if chain[-1]["subject_hash"] != parent["content_hash"]:
                raise DurableError("Evaluation chain hash mismatch")
            seen.add(parent["evaluation_id"])
            chain.append(parent)
        chain.reverse()
        return chain

    def _append_record(self, conn: sqlite3.Connection, attempt_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM attempt_records WHERE attempt_id=?", (attempt_id,)).fetchone()
        value = {"record_id": new_id("record"), "attempt_id": attempt_id, "seq": int(row[0]), "type": kind, "payload": payload, "created_at": utc_now()}
        digest = _digest(value)
        conn.execute("INSERT INTO attempt_records(record_id,attempt_id,seq,type,content_json,content_hash,created_at) VALUES(?,?,?,?,?,?,?)", (value["record_id"], attempt_id, value["seq"], kind, _json(payload), digest, value["created_at"]))
        value["content_hash"] = digest
        return value

    def _record_value(self, row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["payload"] = json.loads(value.pop("content_json"))
        return value

    def _latest_checkpoint_payload(self, attempt_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT content_json FROM attempt_records WHERE attempt_id=? AND type='checkpoint' ORDER BY seq DESC LIMIT 1", (attempt_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def _recovery_source(self, task: dict[str, Any], attempt: dict[str, Any] | None, current: WorkspaceStamp, alignment: str) -> str:
        evaluations = [row[0] for row in self.conn.execute("SELECT evaluation_id FROM evaluations WHERE task_id=? ORDER BY created_at", (task["task_id"],))]
        payload = {
            "task_id": task["task_id"],
            "task_state_version": task["state_version"],
            "contract_head_id": task.get("contract_head_id"),
            "active_attempt_id": task.get("active_attempt_id"),
            "latest_attempt_id": attempt["attempt_id"] if attempt else None,
            "latest_attempt_status": attempt["status"] if attempt else None,
            "attempt_records": [item["content_hash"] for item in attempt["records"]] if attempt else [],
            "attempt_evidence": [item["evidence_id"] for item in attempt["evidence"]] if attempt else [],
            "evaluations": evaluations,
            "acceptance_head_id": task.get("acceptance_head_id"),
            "workspace_stamp": current.content_hash(),
            "workspace_alignment": alignment,
            "decisions": [item["event_id"] for item in self.decisions(task["task_id"])],
        }
        return _digest(payload)

    def _safe_file(self, path: str) -> Path:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or ".metaloop" in relative.parts:
            raise DurableError(f"unsafe workspace path: {path}")
        target = (self.workspace / relative).resolve()
        if not target.is_relative_to(self.workspace) or not target.exists():
            raise DurableError(f"workspace file missing: {path}")
        return target

    def _would_cycle(self, task_id: str, dependency: str) -> bool:
        pending = [dependency]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == task_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(item[0] for item in self.conn.execute("SELECT depends_on FROM task_dependencies WHERE task_id=?", (current,)))
        return False

    def _bump_project(self, conn: sqlite3.Connection) -> None:
        conn.execute("UPDATE projects SET state_version=state_version+1,updated_at=?", (utc_now(),))

    def _meta(self, key: str) -> str | None:
        try:
            row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        except sqlite3.Error:
            return None
        return str(row[0]) if row else None


def _tier_name(level: int) -> str:
    for name, value in ASSURANCE_LEVELS.items():
        if value == level:
            return name
    return "durable_routine"


def _projection(
    status: str,
    *,
    assurance: dict[str, Any],
    authority_sequence: list[str] | None = None,
    pending_authorities: list[str] | None = None,
    resolved_trigger_proofs: dict[str, list[str]] | None = None,
    next_transition: str,
    next_action: str,
    blocker: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "authority_sequence": list(authority_sequence or []),
        "pending_authorities": list(pending_authorities or []),
        "next_transition": next_transition,
        "next_action": next_action,
        "blocker": blocker,
        "resolved_trigger_proofs": dict(resolved_trigger_proofs or {}),
        "assurance": assurance,
    }


def _ordered_authorities(authorities: Any) -> list[str]:
    values = set(authorities)
    unknown = values - set(AUTHORITY_SEQUENCE)
    if unknown:
        raise ValueError("unknown Evaluation authorities: " + ", ".join(sorted(str(item) for item in unknown)))
    return [authority for authority in AUTHORITY_SEQUENCE if authority in values]


def _evaluation_authority_sequence(root: dict[str, Any]) -> list[str] | None:
    required = root["payload"].get("required_authorities", [])
    if not isinstance(required, list) or any(not isinstance(item, str) or item not in AUTHORITY_SEQUENCE for item in required):
        return None
    declared = root["payload"].get("authority_sequence")
    if declared is None:
        return _ordered_authorities(required)
    if (
        not isinstance(declared, list)
        or any(not isinstance(item, str) or item not in AUTHORITY_SEQUENCE for item in declared)
        or len(declared) != len(set(declared))
        or set(declared) != set(required)
        or declared != _ordered_authorities(declared)
    ):
        return None
    return list(declared)


def _unavailable_context() -> dict[str, Any]:
    return {"source": "unavailable", "provider": "unavailable", "context_id": None, "verified": False}


def _context_provenance(context_id: str | None, host_context: dict[str, Any] | None = None) -> dict[str, Any]:
    if context_id:
        return {"source": "manual", "provider": "manual", "context_id": str(context_id), "verified": False}
    if host_context is None:
        return _unavailable_context()
    if not isinstance(host_context, dict):
        raise ValueError("host_context must be an object supplied by a trusted host adapter")
    resolved = host_context.get("context_id")
    provider = host_context.get("provider")
    if not isinstance(resolved, str) or not resolved.strip():
        raise ValueError("host_context.context_id must be a non-empty string")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("host_context.provider must be a non-empty string")
    return {"source": "host", "provider": provider.strip(), "context_id": resolved.strip(), "verified": True}


def _contexts_are_verified_and_distinct(worker: dict[str, Any], reviewer: dict[str, Any]) -> bool:
    return bool(
        _is_verified_host_context(worker)
        and _is_verified_host_context(reviewer)
        and worker.get("context_id")
        and reviewer.get("context_id")
        and worker["context_id"] != reviewer["context_id"]
    )


def _is_verified_host_context(value: dict[str, Any]) -> bool:
    return bool(value.get("source") == "host" and value.get("verified") is True and value.get("context_id"))


def _normalize_review_report(
    report: dict[str, Any],
    *,
    decision: str,
    evaluation: dict[str, Any],
    attempt: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("review report must be an object")
    review_scope = report.get("review_scope")
    if not isinstance(review_scope, str) or not review_scope.strip():
        raise ValueError("review report requires a non-empty review_scope")
    normalized: dict[str, Any] = {"review_scope": review_scope.strip()}
    for key in ("questions_and_findings", "counterexamples_executed", "blocking_findings", "nonblocking_risks"):
        value = report.get(key)
        if not isinstance(value, list):
            raise ValueError(f"review report requires {key} as a list")
        normalized[key] = value
    resolved = report.get("resolved_trigger_ids", [])
    if not isinstance(resolved, list) or any(not isinstance(item, str) or not item.strip() for item in resolved):
        raise ValueError("review report resolved_trigger_ids must be a list of non-empty strings")
    normalized["resolved_trigger_ids"] = sorted({item.strip() for item in resolved})
    declared_decision = report.get("decision")
    if declared_decision is not None and declared_decision != decision:
        raise ValueError("review report decision does not match the Evaluation decision")
    if decision == "approved" and normalized["blocking_findings"]:
        raise ValueError("approved review report cannot contain blocking findings")
    normalized["decision"] = decision
    normalized["governing_artifact_hashes"] = {
        "contract_id": contract["contract_id"],
        "contract_hash": contract["content_hash"],
        "attempt_id": attempt["attempt_id"],
        "attempt_hash": attempt["execution_hash"],
        "evidence": [{"evidence_id": item["evidence_id"], "sha256": item["sha256"]} for item in attempt["evidence"]],
    }
    normalized["exact_evaluation_subject"] = {
        "evaluation_id": evaluation["evaluation_id"],
        "content_hash": evaluation["content_hash"],
    }
    return normalized


def _path_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    output: set[str] = set()
    for item in values:
        if isinstance(item, str):
            output.add(Path(item).as_posix())
        elif isinstance(item, dict) and item.get("path"):
            output.add(Path(str(item["path"])).as_posix())
    return output


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
