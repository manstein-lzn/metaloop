# MetaLoop V2 Team Trial Guide

Date: 2026-07-20

MetaLoop v2 is ready for real project trial as a self-contained Codex Skill.
It is a durable work protocol, not a multi-agent runtime or project manager.

## Distribution

Install `skills/metaloop/` to `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`.
The directory includes the thin kernel, generated canonical core, references,
extensions, and read-only dashboard. See
[codex_install_metaloop_skill.md](codex_install_metaloop_skill.md).

## Use

```text
Use $metaloop. I want to <task>.
```

The Skill should inspect the project, resolve a Task, lock a ContractRevision,
maintain one recoverable open Attempt, record exact evidence and decisions, and
use a content-bound Evaluation chain for completion. Users should not need to
name these mechanisms.

## Trial Scenarios

- Continue one task across context compaction during an open Attempt.
- Pause Task A, finish Task B, then resume A without reading chat history.
- Spawn a repair child, complete it, and verify the parent remains open.
- Refresh a parent RecoveryView, complete its dependency, and verify the parent
  becomes stale before resumption.
- Record a Project decision, refresh RecoveryView, and verify the decision
  remains in `current_decisions` after delta watermarks advance.
- Intentionally retry an exact Attempt and judge whether `retry_reason` is
  helpful or annoying.
- Let two threads update the same Task with stale versions and confirm one
  fails cleanly.
- Change a verified artifact before acceptance and confirm the old Evaluation
  is rejected.
- Initialize v2, then try a v1 context/event/thread write and confirm it routes
  to explicit v2 state or fails closed.

## Feedback

Report concrete examples of:

- missing or excessive RecoveryView information;
- unclear Attempt boundaries;
- duplicate fingerprint false positives/negatives;
- friction selecting or switching Tasks;
- DecisionEvents that should have been task- or project-scoped;
- CAS conflicts that were confusing rather than protective;
- v1 migration records that could not be interpreted correctly.

Do not request scheduler, vector memory, dashboards with mutation, priority,
deadline, or agent-pool features without repeated task evidence that the core
protocol cannot solve the observed failure.
