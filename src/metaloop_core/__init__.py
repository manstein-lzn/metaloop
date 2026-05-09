"""Stable MetaLoop protocol core APIs.

This package is intentionally smaller than the full ``metaloop`` package.
It owns portable state and protocol primitives that can be reused by the
Codex Skill, future wrappers, and the legacy full-repository CLI.
"""

from metaloop_core.event_log import EventLog
from metaloop_core.execution import build_execution_report, load_execution_report, write_execution_report
from metaloop_core.ids import new_id, utc_now
from metaloop_core.repair_redesign import classify_dissatisfaction
from metaloop_core.thread_registry import ThreadRegistry
from metaloop_core.verification import VerificationSummary, load_verification_summary, verify_workspace
from metaloop_core.workspace import WorkspacePaths, WorkspaceState

__all__ = [
    "EventLog",
    "ThreadRegistry",
    "VerificationSummary",
    "WorkspacePaths",
    "WorkspaceState",
    "build_execution_report",
    "classify_dissatisfaction",
    "load_execution_report",
    "load_verification_summary",
    "new_id",
    "utc_now",
    "verify_workspace",
    "write_execution_report",
]
