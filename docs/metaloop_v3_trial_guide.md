# MetaLoop v3.2 Alpha Trial Guide

MetaLoop v3.2 is a minimal, orthogonal, event-triggered outer-loop control
system, not a scheduler or project manager. It trusts the Agent and adds durable
memory or a fresh observation only when an observed risk justifies it.

## Entry

```text
Use $metaloop. I want to <task>.
```

The Skill chooses Tier 1-3, locks a ContractRevision, and keeps the Attempt
recoverable. Explicit invocation is at least Tier 1. Atomic Tier 0 work makes no
kernel calls. Users do not choose tiers or name internal records.

## Scenarios

- Run a routine local repair through `task begin`, one edit, and `attempt finish`.
  Record the number of explicit protocol commands and time spent on protocol work.
- Sample atomic Tier 0 work externally and confirm MetaLoop SQLite has no Task for
  it.
- Run a cross-module or schema change with a complete executable oracle at Tier 2
  and confirm reviewer authority is not added merely because the change is formal.
- Run a semantic change with an incomplete oracle at Tier 3. Confirm mechanical
  verification reports `mechanically_verified_pending_reviewer` and cannot be
  presented as acceptance-ready.
- Set `METALOOP_HOST_CONTEXT_ID` to distinct Worker and reviewer values and use a
  structured report. Confirm the report contains exact Contract, Attempt,
  Evidence, and parent Evaluation hashes.
- Pass distinct manual `--context-id` values and confirm both remain
  `manual/unverified`, Tier 3 acceptance is blocked, and the same Task can start
  a repair Attempt.
- Create a `needs_changes` Review, then try to review or accept its stale parent.
  Confirm only the active Evaluation head is usable and repair stays in the same
  Task.
- Require reviewer and reserved user authority. Confirm the only sequence is
  verification -> reviewer -> user -> accept, every head transition increments
  Task state version, and extra or out-of-order Review fails closed.
- Load a historical `needs_changes -> approved` or user-before-reviewer chain.
  Confirm Recovery exposes `start_repair_attempt`, preserves every immutable
  Evaluation, and the projected transition succeeds.
- Resolve every Tier 3 trigger in a new evidence-bound ContractRevision and
  confirm each trigger has a mapped passing validator or verified reviewer proof
  and the old Attempt/Evaluation can no longer be accepted. Confirm a plain
  passing `true` validator cannot resolve an unmapped trigger.
- Snapshot `.git` metadata around `observe` and Recovery calls. Confirm index,
  objects, refs, and lock files do not change.
- Commit the exact accepted content and confirm Recovery remains fresh/aligned
  without a promotion Task.
- Add uncheckpointed content before commit and confirm promotion fails closed.
- Fail a validator, correct the implementation in a new Attempt under the same
  Task, and confirm no repair Task is created solely for the failure.
- Correct a defective validator through a new ContractRevision in the same Task.
- Apply reviewer changes in the same Task and require Review only for the final
  semantic claim.
- Start a long Attempt, edit a file, observe `ahead`, then claim/defer/assign it
  in a checkpoint before continuing.
- Pause Task A, work on Task B in a separate worktree, then return to A.
- Create a repair child and confirm it cannot complete its parent.
- Change a stable input and confirm lifecycle gates fail closed.
- Change a managed output after Evidence and confirm rejection.
- Add reviewer authority and require a linear approved overlay.
- Switch branch or reset HEAD and confirm `conflicted`.
- Break Git or exceed scan limits and confirm `unknown`.
- Trigger context compaction after a checkpoint and resume from RecoveryView.
- Repeat an exact sealed Attempt and require a concrete retry reason.

## Feedback

For Tier 1-3, record the concrete Task, control status, changed paths, expected
behavior, explicit command count, Task/Attempt churn, authority waits, protocol
time, reviewer findings, user-first escaped findings, recovery duplication, and
unnecessary user interruptions. Evaluate Tier 0 only through voluntary trial
logs, Git sampling, or user study; zero-kernel work cannot be measured from
MetaLoop SQLite.

Do not request background scheduling, transcript storage, vector memory, semantic
keyword routing, or a project-management UI without repeated evidence that the
final protocol cannot solve the observed failure.
