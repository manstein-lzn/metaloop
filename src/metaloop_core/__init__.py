"""Stable MetaLoop protocol core APIs.

This package owns portable state and protocol primitives for the self-contained
Codex Skill and any future thin wrappers that need the same `.metaloop/` truth.
"""

from metaloop_core.adaptive_loop import AdaptiveIteration, AdaptiveLoopState, append_iteration, decide_next, load_adaptive_loop, new_adaptive_loop, record_iteration, write_adaptive_loop
from metaloop_core.activation import activate_once, activation_lease_path, activation_result_path, plan_activation, write_activation_result
from metaloop_core.control import control_request_path, load_control_requests, pending_control_requests, write_control_request
from metaloop_core.context import context_dir, context_file_path, context_summary, ensure_context_files, read_context_file, write_context_file
from metaloop_core.event_log import EventLog
from metaloop_core.execution import build_execution_report, load_execution_report, write_execution_report
from metaloop_core.feedback import DiagnosisReport, ObservationReport, diagnose_next, observe_workspace, write_diagnosis_report, write_observation_report
from metaloop_core.ids import new_id, utc_now
from metaloop_core.observe import observe_node, observe_root
from metaloop_core.repair_redesign import classify_dissatisfaction
from metaloop_core.relay import load_dispatch_map, load_outbox_items, relay_outbox, validate_dispatch_map, write_relay_result
from metaloop_core.routing import job_envelope_hash, latest_adaptive_decision, route_next_hop, route_workspace, validate_global_blackboard, validate_job_envelope
from metaloop_core.tick import tick_workspace, write_tick_result
from metaloop_core.thread_registry import ThreadRegistry
from metaloop_core.verification import VerificationSummary, build_review_result, load_review_result, load_verification_summary, verify_workspace, write_review_result
from metaloop_core.workspace import WorkspacePaths, WorkspaceState

__all__ = [
    "EventLog",
    "AdaptiveIteration",
    "AdaptiveLoopState",
    "DiagnosisReport",
    "ObservationReport",
    "ThreadRegistry",
    "VerificationSummary",
    "WorkspacePaths",
    "WorkspaceState",
    "activate_once",
    "activation_lease_path",
    "activation_result_path",
    "append_iteration",
    "build_execution_report",
    "build_review_result",
    "classify_dissatisfaction",
    "control_request_path",
    "context_dir",
    "context_file_path",
    "context_summary",
    "decide_next",
    "diagnose_next",
    "ensure_context_files",
    "load_adaptive_loop",
    "load_control_requests",
    "load_dispatch_map",
    "load_execution_report",
    "load_outbox_items",
    "load_review_result",
    "load_verification_summary",
    "job_envelope_hash",
    "latest_adaptive_decision",
    "new_adaptive_loop",
    "new_id",
    "observe_node",
    "observe_root",
    "observe_workspace",
    "relay_outbox",
    "record_iteration",
    "read_context_file",
    "route_next_hop",
    "route_workspace",
    "tick_workspace",
    "utc_now",
    "verify_workspace",
    "validate_dispatch_map",
    "validate_global_blackboard",
    "validate_job_envelope",
    "pending_control_requests",
    "plan_activation",
    "write_adaptive_loop",
    "write_activation_result",
    "write_control_request",
    "write_context_file",
    "write_diagnosis_report",
    "write_execution_report",
    "write_observation_report",
    "write_relay_result",
    "write_review_result",
    "write_tick_result",
]
