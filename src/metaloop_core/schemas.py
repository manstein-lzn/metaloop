from __future__ import annotations

CAPSULE_SCHEMA = "metaloop.lightweight_capsule"
ADAPTIVE_LOOP_SCHEMA = "metaloop.adaptive_goal_loop"
ADAPTIVE_ITERATION_SCHEMA = "metaloop.adaptive_goal_iteration"
OBSERVATION_REPORT_SCHEMA = "metaloop.observation_report"
DIAGNOSIS_REPORT_SCHEMA = "metaloop.diagnosis_report"
EXECUTION_REPORT_SCHEMA = "metaloop.lightweight_execution_report"
EXTENSION_SPEC_SCHEMA = "metaloop.extension_spec"
VERIFICATION_SPEC_SCHEMA = "metaloop.verification_spec"
VERIFICATION_SCHEMA = "metaloop.lightweight_verification_result"
THREAD_REGISTRY_SCHEMA = "metaloop.thread_registry"
EVENT_SCHEMA = "metaloop.event"
JOB_ENVELOPE_SCHEMA = "metaloop.job_envelope"
GLOBAL_BLACKBOARD_SCHEMA = "metaloop.global_blackboard"
TICK_RESULT_SCHEMA = "metaloop.tick_result"
DISPATCH_MAP_SCHEMA = "metaloop.dispatch_map"
RELAY_RESULT_SCHEMA = "metaloop.relay_result"
NODE_SUMMARY_SCHEMA = "metaloop.node_summary"
GLOBAL_SUMMARY_SCHEMA = "metaloop.global_summary"
CONTROL_REQUEST_SCHEMA = "metaloop.control_request"
ACTIVATION_RESULT_SCHEMA = "metaloop.activation_result"
ACTIVATION_LEASE_SCHEMA = "metaloop.activation_lease"
CONTEXT_SUMMARY_SCHEMA = "metaloop.context_summary"

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

ROUTE_ACTIONS = {"dispatch", "loop_back", "route_to", "escalate", "suspend", "wait", "diagnose", "error"}
ROUTABLE_VERIFICATION_STATUSES = {
    "completed_verified",
    "execution_incomplete",
    "failed",
    "human_acceptance_required",
    "invalid_capsule",
    "missing_execution_report",
    "missing_verification_plan",
    "unsupported_verification_spec",
}

CONTROL_TYPES = {"halt", "resource_approval", "inject_fact", "revise_contract_request"}
ACTIVATION_ACTIONS = {
    "blocked_by_control",
    "failed",
    "lease_active",
    "no_worker_command",
    "ready",
    "skipped_no_envelope",
    "started",
}

CONTEXT_FILE_NAMES = {
    "current_hypothesis.md",
    "failed_attempts.md",
    "project_brief.md",
    "resume_brief.md",
}
