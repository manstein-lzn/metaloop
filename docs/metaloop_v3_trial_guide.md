# MetaLoop v3.1 Alpha Trial Guide

MetaLoop v3.1 is a risk-proportional Git-backed durable protocol, not a scheduler
or project manager.

## Entry

```text
Use $metaloop. I want to <task>.
```

The Skill chooses a proportionate Frame, locks a ContractRevision, and keeps the
Attempt recoverable. Users do not need to name internal records.

## Scenarios

- Run a routine local repair through `task begin`, one edit, and `attempt finish`.
  Record the number of explicit protocol commands and time spent on protocol work.
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

Record the concrete Task, current state, changed paths, expected behavior,
explicit MetaLoop command count, Task/Attempt churn, promotion Task count,
authority waits, protocol time, and the real defects caught by gates. Include a
reproduction for recovery gaps, reconcile friction, stable/managed reference
burden, authority confusion, installation failures, and host safe-point behavior.

Do not request background scheduling, transcript storage, vector memory, semantic
keyword routing, or a project-management UI without repeated evidence that the
final protocol cannot solve the observed failure.
