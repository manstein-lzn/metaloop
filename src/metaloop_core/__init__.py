"""Stable MetaLoop protocol core APIs.

This package is intentionally smaller than the full ``metaloop`` package.
It owns portable state and protocol primitives that can be reused by the
Codex Skill, future wrappers, and the legacy full-repository CLI.
"""

from metaloop_core.event_log import EventLog
from metaloop_core.adaptive_loop import AdaptiveIteration, AdaptiveLoopState, append_iteration, decide_next, load_adaptive_loop, new_adaptive_loop, record_iteration, write_adaptive_loop
from metaloop_core.execution import build_execution_report, load_execution_report, write_execution_report
from metaloop_core.ids import new_id, utc_now
from metaloop_core.repair_redesign import classify_dissatisfaction
from metaloop_core.thread_registry import ThreadRegistry
from metaloop_core.verification import VerificationSummary, load_verification_summary, verify_workspace
from metaloop_core.workspace import WorkspacePaths, WorkspaceState

__all__ = [
    "EventLog",
    "AdaptiveIteration",
    "AdaptiveLoopState",
    "ThreadRegistry",
    "VerificationSummary",
    "WorkspacePaths",
    "WorkspaceState",
    "append_iteration",
    "build_execution_report",
    "classify_dissatisfaction",
    "decide_next",
    "load_adaptive_loop",
    "load_execution_report",
    "load_verification_summary",
    "new_adaptive_loop",
    "new_id",
    "record_iteration",
    "utc_now",
    "verify_workspace",
    "write_adaptive_loop",
    "write_execution_report",
]
