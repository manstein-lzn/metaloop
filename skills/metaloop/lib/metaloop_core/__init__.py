"""MetaLoop v3.4 canonical Git-backed durable protocol APIs."""

from metaloop_core.contracts import contract_assurance, contract_hash, managed_output_paths, normalize_contract, validate_contract, verify_stable_inputs
from metaloop_core.decisions import validate_decision, validate_event_type
from metaloop_core.durable import ConflictError, DuplicateAttemptError, DurableError, DurableStore, InvalidTransitionError, NotFoundError
from metaloop_core.host import safe_point
from metaloop_core.recovery import recovery_view, write_recovery
from metaloop_core.verification import verify_attempt
from metaloop_core.workspace import GitWorkspace, GitWorkspaceError, WorkspaceIdentity, WorkspaceStamp, alignment_reason, changed_paths_between, compare_stamps, is_content_preserving_commit, workspace_identity, workspace_stamp

__all__ = [
    "ConflictError",
    "DuplicateAttemptError",
    "DurableError",
    "DurableStore",
    "GitWorkspace",
    "GitWorkspaceError",
    "InvalidTransitionError",
    "NotFoundError",
    "WorkspaceIdentity",
    "WorkspaceStamp",
    "alignment_reason",
    "changed_paths_between",
    "compare_stamps",
    "contract_assurance",
    "contract_hash",
    "managed_output_paths",
    "normalize_contract",
    "recovery_view",
    "safe_point",
    "is_content_preserving_commit",
    "validate_contract",
    "validate_decision",
    "validate_event_type",
    "verify_attempt",
    "verify_stable_inputs",
    "workspace_identity",
    "workspace_stamp",
    "write_recovery",
]
