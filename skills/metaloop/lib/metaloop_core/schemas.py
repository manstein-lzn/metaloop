from __future__ import annotations

SCHEMA_VERSION = 3
PROTOCOL_VERSION = "3.4"
PROJECT_SCHEMA = "metaloop.final.project"
TASK_SCHEMA = "metaloop.final.task"
CONTRACT_SCHEMA = "metaloop.final.contract"
ATTEMPT_SCHEMA = "metaloop.final.attempt"
CHECKPOINT_SCHEMA = "metaloop.final.checkpoint"
EVIDENCE_SCHEMA = "metaloop.final.evidence"
DECISION_SCHEMA = "metaloop.final.decision"
EVALUATION_SCHEMA = "metaloop.final.evaluation"
WORKSPACE_STAMP_SCHEMA = "metaloop.final.workspace_stamp"
RECOVERY_SCHEMA = "metaloop.final.recovery"

TASK_STATES = {"open", "paused", "completed", "cancelled"}
ATTEMPT_STATES = {"open", "sealed", "aborted"}
EVALUATION_DECISIONS = {"approved", "rejected", "needs_changes"}
DECISIONS = {"complete", "continue", "repair", "redesign", "pivot", "stop", "escalate"}
DECISION_TYPES = {"observation", "diagnosis", "decision", "next_plan", "blocker", "handoff", "note"}
ALIGNMENT_STATES = {"aligned", "ahead", "conflicted", "unknown"}
CHANGE_KINDS = {"repair", "extension", "redesign"}
SCOPE_ROLES = {"governing_document", "module_contract", "migration_plan", "implementation", "test_contract"}

CONTRACT_VERSION = "1.1"
LEGACY_CONTRACT_VERSION = "1.0"
ASSURANCE_LEVELS = {
    "durable_routine": 1,
    "governed": 2,
    "high_assurance": 3,
}
ASSURANCE_TIERS = set(ASSURANCE_LEVELS)
AUTHORITIES = {"reviewer", "user"}
