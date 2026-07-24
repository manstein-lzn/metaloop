# MetaLoop v3.4 Alpha Trial Guide

MetaLoop v3.4 is a minimal, orthogonal, event-triggered outer-loop control
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

- Run ordinary local edits, documentation syncs, and test-only repairs without
  MetaLoop. Confirm Git and the project verifier are sufficient and no Task is
  created.
- Run a durable routine repair through `task begin --check <project verifier>`,
  one edit, and `attempt finish` without authoring a Contract JSON file.
  Record the number of explicit protocol commands and time spent on protocol work.
- Change several ordinary implementation and test files, then run `attempt
  finish` without `--claimed-path`. Confirm all current-Attempt deltas are
  reconciled while only managed outputs become Evidence.
- Interrupt `attempt finish` after checkpoint, Evidence, seal, or verification,
  then repeat the identical command. Confirm it resumes without duplicate
  checkpoint, Evidence, or Evaluation records.
- Abort or supersede an Attempt while its non-conflicted work remains in the
  workspace. Start the next same-Task Attempt without enumerating inherited
  paths. Confirm source baseline/checkpoint/adopted hashes and per-path
  provenance are recorded even when the source was already checkpointed. Narrow
  the next Contract and confirm an out-of-scope carried path blocks Attempt
  creation without leaving partial state.
- Sample atomic Tier 0 work externally and confirm MetaLoop SQLite has no Task for
  it.
- Run a cross-module or schema change with a complete executable oracle at Tier 2
  and confirm reviewer authority is not added merely because the change is formal.
- Run implementation for an architecture or cross-module change at Tier 1/2
  when its completion is mechanically decidable. Confirm the subject matter
  alone does not trigger Review.
- Run a semantic claim with an incomplete oracle at Tier 3. Confirm mechanical
  verification reports `mechanically_verified_pending_reviewer` and waits for a
  structured reviewer report. Confirm finish and resumed observation derive the
  same minimal `review_handoff` and current `active_chain` without a write.
- Use a structured report without any host configuration. Confirm the report
  contains exact Contract, Attempt, Evidence, and parent Evaluation hashes and
  Tier 3 can complete when the report is approved.
- Optionally pass a `--context-id` label and confirm it is diagnostic only and
  does not change acceptance behavior.
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
  confirm the approved reviewer report lists every `resolved_trigger_id` and
  the old Attempt/Evaluation can no longer be accepted. Confirm a plain passing
  validator cannot resolve an unmapped trigger.
- Snapshot `.git` metadata around `observe` and Recovery calls. Confirm index,
  objects, refs, and lock files do not change.
- Commit the exact accepted content and confirm Recovery remains fresh/aligned
  without a promotion Task.
- Add uncheckpointed content before commit and confirm promotion fails closed.
- Fail a validator, correct the implementation in a new Attempt under the same
  Task, and confirm the latest workspace is automatically adopted without a
  repair Task or manual inherited-path handling.
- Correct a defective validator through a new ContractRevision in the same Task.
- Submit a malformed manual validator to `task begin` and confirm validation
  fails transactionally with no empty Task. Reserve user authority only in the
  assurance block, never in a validator or resource gate.
- Submit missing command/path/hash fields, unsafe validator paths, invalid
  timeout/manual authority, a non-object resource gate, and a blank `--check`;
  confirm each fails before Task creation. Catch a composed
  begin failure inside an ambient transaction and confirm savepoint rollback
  still leaves no partial Task or default selection.
- Apply reviewer changes in the same Task and require Review only for the final
  semantic claim.
- Start a long Attempt, edit a file, observe `ahead`, then claim/defer/assign it
  in a checkpoint before continuing. Confirm brief integrity is
  `not_yet_reconciled`, not `violated`, while seal and acceptance remain blocked.
- Attach an optional external locator and checkpoint identity. Confirm Recovery
  preserves the locator across same-Task adoption, never polls it, and rejects
  domain progress fields such as `last_completed_epoch`.
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

Treat `begin + finish` as the Tier 1 Agent-facing budget. Use derived
`protocol_activity` as a churn proxy. Use a 10% protocol-time warning only when
the host can measure active work time; never turn the warning into an
acceptance gate or add state writes solely for telemetry.

Do not request background scheduling, transcript storage, vector memory, semantic
keyword routing, or a project-management UI without repeated evidence that the
final protocol cannot solve the observed failure.
