# MetaLoop V2 Team Trial Guide

Date: 2026-07-20

MetaLoop v2 is ready for real project trial as a self-contained Codex Skill.
It combines deep design and Progressive Design discipline with a durable work
graph. It is not a multi-agent runtime or project manager.

## Distribution

Use the Codex install prompt in
[codex_install_metaloop_skill.md](codex_install_metaloop_skill.md). Install
`skills/metaloop/` to `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`.

This format lets Codex adapt installation to the target machine, validate the
thin kernel and vendored core, and run v1/v2 smoke tests. Replace the complete
MetaLoop Skill directory; do not update individual files.

## Use

```text
Use $metaloop. I want to <task>.
```

The Skill should inspect the project, choose the smallest sufficient protocol,
resolve a Task, lock a ContractRevision, maintain one recoverable open Attempt,
record exact evidence and decisions, and use a content-bound Evaluation chain
for completion. Users should not need to name these mechanisms.

For tiny one-step edits, ordinary Codex remains sufficient.

## Trial Scenarios

- Continue one task across context compaction during an open Attempt.
- Pause Task A, finish Task B, then resume A without reading chat history.
- Spawn a repair child, complete it, and verify the parent remains open.
- Complete a dependency and verify the parent RecoveryView becomes stale.
- Record a Project decision and verify it remains in `current_decisions` after
  delta watermarks advance.
- Intentionally retry an exact Attempt and judge `retry_reason` ergonomics.
- Let two threads update the same Task with stale versions and confirm one
  fails cleanly.
- Change a verified artifact before acceptance and confirm rejection.
- Use Progressive Design on a broad architecture goal and inspect whether the
  selected slice preserves the full direction without creating excess process.
- Use optional V2 governance on an architecture-sensitive Task, drift a stable
  module contract, and confirm start/seal/verify/review/accept fail closed.

## Feedback

Report concrete examples of:

- missing or excessive RecoveryView information;
- unclear Task or Attempt boundaries;
- duplicate fingerprint false positives/negatives;
- friction selecting, switching, or repairing Tasks;
- DecisionEvents with the wrong Task/Project scope;
- CAS conflicts that were confusing rather than protective;
- Progressive Design that felt too heavy or too shallow;
- governance fields that prevented real drift or merely added ceremony;
- v1 migration records that could not be interpreted correctly.

Do not request scheduler, vector memory, mutating dashboards, priority,
deadline, or agent-pool features without repeated task evidence that the core
protocol cannot solve the observed failure.

## Positioning

Use this wording:

```text
MetaLoop v2 trial: a self-contained Codex Skill for deep design, progressive
delivery, durable task recovery, and content-bound verification.
```

Avoid claiming production multi-agent runtime, fully non-bypassable enforcement,
automatic semantic memory, or a complete domain verification ecosystem.
