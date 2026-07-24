# MetaLoop v3.4 Final Protocol

MetaLoop v3.4 binds one local Git worktree to one SQLite Project. Git supplies
mechanical workspace identity; SQLite supplies protocol history and authority.

The default route is outside MetaLoop: ordinary local edits, documentation
synchronization, and test-only repairs use Git plus the project's verifier. A
MetaLoop Task is justified only by durable recovery, task switching, managed
Evidence, formal sealing, or a semantic Review.

```text
Project -> Task -> ContractRevision -> Attempt -> Evidence -> Evaluation
                                     -> Checkpoint
                -> DecisionEvent
RecoveryView is derived from these records plus the live WorkspaceStamp.
```

The lifecycle is `Frame -> Work -> Reconcile -> Adapt -> Prove`. Completion is
valid only when the live workspace equals the latest acknowledged checkpoint,
all stable inputs and evidence retain their hashes, locked validators pass, and
every required authority appears in the one active Evaluation chain.

Workspace alignment is `aligned`, `ahead`, `conflicted`, or `unknown`. An exact
direct commit may remain aligned when the prior materialized worktree tree
equals the new HEAD tree and the new index/worktree are clean. Only `aligned`
may pass seal, verification, review, or acceptance. Integrity projects `valid`,
`not_yet_reconciled`, or `violated`: ordinary `ahead` work in the active Attempt
is pending reconciliation rather than corruption, while conflict, unknown
state, identity/hash drift, and closed-claim drift are violations. The adapter
excludes `.git/` and `.metaloop/` from generic project
change observation, while managed outputs and Evidence are checked directly.
Observation computes temporary trees through a repository-external index and
object directory, with the real object store available only as an alternate.

RecoveryView is live-derived and fresh whenever canonical sources can be read
and workspace alignment is aligned. A stored resume annotation is optional.
Later Tier 0 Git work may make a completed Task's historical RecoveryView stale,
but default Project integrity does not treat that as protocol corruption.
Explicit Task integrity still compares the sealed claim with current files.

Assurance applies to the completion claim, not permission to implement. Tier 0
uses no protocol; Tier 1 adds
durable continuity and executable proof; Tier 2 adds stable inputs, stronger
validators, and exact Evidence as needed; Tier 3 adds fresh-context Review for
semantic claims with incomplete executable oracles. `task begin` and `attempt
finish` compose low-level mutations for routine work without weakening or
duplicating the underlying records. Subject matter such as architecture,
schemas, cross-module code, or performance work does not itself trigger Tier 3.

New Contract v1.1 content carries normalized assurance. Tier 3 reviewer
authority is kernel-derived and its unresolved trigger IDs remain sticky until
a new ContractRevision binds explicit resolution evidence. A resolution must
cover every trigger with an approved structured reviewer report whose
`resolved_trigger_ids` names the trigger explicitly. Passing validators remain
mechanical evidence but do not silently resolve semantic trigger memory.
Legacy Contract v1.0 content remains readable without acquiring new authority
retroactively.

The existing Task `acceptance_head_id` is the current Evaluation pointer before
and after completion. Verification may supersede the prior failed candidate;
Review must extend the current head; acceptance must consume it. A new Attempt
or ContractRevision clears the old candidate while retaining immutable history.

`task begin` atomically composes Task, ContractRevision, selection, and Attempt
creation. Contract or input validation failure rolls back the whole composition
and cannot leave an empty Task. Technical correctness remains owned by the
project verifier; MetaLoop stores completion proof and recovery state instead
of duplicating domain checks.

Tier 1 may generate its minimal Contract from the Task title, plan, and optional
project-native `--check` commands. Tier 2/3 keep explicit Contract JSON for
managed sealing, stronger policy, and reserved authority. Blank checks are
rejected, no-check completion is explicitly non-technical, and generated
Contracts do not infer change kind.

`attempt finish` is the resumable routine closure entry. It automatically
claims workspace delta created after the current Attempt baseline except paths
explicitly deferred or assigned, binds declared managed outputs and explicit
artifacts as Evidence, checkpoints, seals, verifies, and accepts when authority
permits. Repeating the command reuses existing checkpoint, Evidence, sealed
Attempt, and Evaluation rather than duplicating them.

Starting a new Attempt may automatically adopt the current non-conflicted
workspace from the latest terminal Attempt in the same Task. The immutable
attempt-start record binds source Attempt/Contract/status hashes, source and
adopted WorkspaceStamp hashes, and per-path source/adopted states. Adoption
derives carried paths across the source baseline, latest checkpoint, and current
workspace, and validates them against the current Contract before creating the
Attempt. It never permits conflicted or unknown workspace state, cross-Task
sources, or scope escape.

Tier 3 Review stores its structured report, optional diagnostic context label,
exact parent Evaluation, Contract, Attempt, and Evidence identities inside the
Review Evaluation content hash. Context metadata is observational only; the
protocol trusts the Agent and does not require host attestation.

When reviewer authority is the next transition, finish and recovery derive a
minimal `review_handoff` from those immutable records. It contains the current
claim, trigger focus, validator summary, reconciled paths, Evidence, active
Evaluation chain, and an empty report template. The handoff is not stored and
has no authority of its own. Routine recovery likewise projects only the active
head lineage unless full history is explicitly requested.

A checkpoint may carry one optional external locator and checkpoint identity.
This metadata is for recovery navigation only. External manifests remain the
authority for progress, liveness, metrics, and completion; MetaLoop does not
schedule or monitor the referenced process.

The active head has one deterministic outer transition: `verify`,
`review:reviewer`, `review:user`, `accept`, or `start_repair_attempt`. Mechanical
verification must precede reviewer authority, which must precede a reserved
user decision. Non-approved and malformed historical chains are terminal for
that candidate and recover through a new Attempt; immutable history is never
rewritten.

One worktree permits one open mutating Attempt. Separate worktrees produce
separate Project identities. MetaLoop never infers Task ownership or semantic
decisions from prose or keywords. An explicit same-Task start/finish is the
cooperative Agent's ownership confirmation for mechanically observed delta.

`protocol_activity` is a read-derived count surface. Routine work budgets two
Agent-facing lifecycle commands and emits a routing warning for repeated
Attempts or checkpoints. MetaLoop does not add telemetry state or enforce a
wall-clock ratio that the host cannot measure reliably.
