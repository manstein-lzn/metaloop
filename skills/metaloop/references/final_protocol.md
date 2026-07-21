# MetaLoop v3.2 Final Protocol

MetaLoop v3.2 binds one local Git worktree to one SQLite Project. Git supplies
mechanical workspace identity; SQLite supplies protocol history and authority.

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
equals the new HEAD tree and the new index/worktree are clean. Only
`aligned` may pass seal, verification, review, acceptance, or selected Task
integrity. The adapter excludes `.git/` and `.metaloop/` from generic project
change observation, while managed outputs and Evidence are checked directly.
Observation computes temporary trees through a repository-external index and
object directory, with the real object store available only as an alternate.

RecoveryView is live-derived and fresh whenever canonical sources can be read
and workspace alignment is aligned. A stored resume annotation is optional.

Assurance is additive in the same ontology: Tier 0 uses no protocol; Tier 1 adds
durable continuity and executable proof; Tier 2 adds stable inputs, stronger
validators, and exact Evidence as needed; Tier 3 adds fresh-context Review for
semantic claims with incomplete executable oracles. `task begin` and `attempt
finish` compose low-level mutations for routine work without weakening or
duplicating the underlying records.

New Contract v1.1 content carries normalized assurance. Tier 3 reviewer
authority is kernel-derived and its unresolved trigger IDs remain sticky until
a new ContractRevision binds explicit resolution evidence. A resolution must
cover every trigger with a passing validator carrying stable `validator_id` and
`resolves_trigger_ids`, or with a host-verified structured reviewer report.
Legacy Contract v1.0 content remains readable without acquiring new authority
retroactively.

The existing Task `acceptance_head_id` is the current Evaluation pointer before
and after completion. Verification may supersede the prior failed candidate;
Review must extend the current head; acceptance must consume it. A new Attempt
or ContractRevision clears the old candidate while retaining immutable history.

Tier 3 Review stores its structured report, context provenance, exact parent
Evaluation, Contract, Attempt, and Evidence identities inside the Review
Evaluation content hash. Context provenance proves a fresh host context for
cognitive independence; it is not a zero-trust authentication system. A naked
CLI `--context-id` is manual and unverified; only a host adapter or
`METALOOP_HOST_CONTEXT_ID` can produce verified host provenance.

The active head has one deterministic outer transition: `verify`,
`review:reviewer`, `review:user`, `accept`, or `start_repair_attempt`. Mechanical
verification must precede reviewer authority, which must precede a reserved
user decision. Non-approved and malformed historical chains are terminal for
that candidate and recover through a new Attempt; immutable history is never
rewritten.

One worktree permits one open mutating Attempt. Separate worktrees produce
separate Project identities. MetaLoop never infers Task ownership or semantic
decisions from paths, prose, or keywords.
