from __future__ import annotations

CAPSULE_SCHEMA = "metaloop.lightweight_capsule"
ADAPTIVE_LOOP_SCHEMA = "metaloop.adaptive_goal_loop"
ADAPTIVE_ITERATION_SCHEMA = "metaloop.adaptive_goal_iteration"
EXECUTION_REPORT_SCHEMA = "metaloop.lightweight_execution_report"
EXTENSION_SPEC_SCHEMA = "metaloop.extension_spec"
VERIFICATION_SPEC_SCHEMA = "metaloop.verification_spec"
VERIFICATION_SCHEMA = "metaloop.lightweight_verification_result"
THREAD_REGISTRY_SCHEMA = "metaloop.thread_registry"
EVENT_SCHEMA = "metaloop.event"

CAPSULE_STATUSES = {"designed", "running", "executed", "repair_required", "redesign_required", "blocked", "completed"}
THREAD_STATUSES = {"active", "paused", "closed", "handoff_required"}
CANONICAL_THREAD_TYPES = {"interface", "design", "worker", "reviewer", "verifier"}
EVENT_TYPES = {"observation", "decision", "action", "blocker", "handoff", "verification", "repair", "redesign", "note"}
KNOWN_EXECUTABLE_VALIDATORS = {
    "artifact_hash",
    "command",
    "file_contains",
    "file_exists",
    "forbidden_path",
    "json_field_exists",
    "json_metric_gate",
}
KNOWN_MANUAL_VALIDATORS = {"forbidden_claim", "manual_acceptance", "resource_gate"}
MODES = {"executable", "manual", "unsupported"}
SEVERITIES = {"blocking", "advisory"}

REPAIR_DECISIONS = {"repair", "redesign", "resume", "complete"}
ADAPTIVE_LOOP_STATUSES = {"active", "completed", "stopped", "blocked"}
ADAPTIVE_DECISIONS = {"complete", "continue", "repair", "redesign", "pivot", "stop", "escalate"}
EVALUATION_STATUSES = {"satisfied", "not_satisfied", "partial", "unknown", "blocked", "invalid_goal"}
