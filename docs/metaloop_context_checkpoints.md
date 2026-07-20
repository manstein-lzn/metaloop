# MetaLoop Context Checkpoints

Date: 2026-05-12

## V2 Update

For v2 Tasks, `.metaloop/metaloop.db` stores the canonical Task head, open
Attempt checkpoints, Evaluation chain, DecisionEvent cursors, and Recovery
Head. The human-readable resume projection is freshness-checked against those
sources and exported under `.metaloop/v2/tasks/<task_id>/resume.md`.

The root `.metaloop/context/*.md` files below remain the v1 compatibility
surface. They are never canonical and should not be used in place of
`recover show` when a v2 Task exists.

Long-running Codex work must survive context growth, thread reset, and handoff
without turning MetaLoop into a memory system. Context checkpoints are small
Markdown summaries under `.metaloop/context/` that make the next Codex agent
productive quickly.

## Principle

```text
Codex keeps rich working context.
MetaLoop keeps compact recovery context.
In v1 only, Mission Capsule remains task truth.
In v1 only, VerificationSpec remains completion truth.
```

The checkpoint files are not a transcript and not a second blackboard. They are
the short read-first layer before a new agent reads full logs.

## Files

The minimal checkpoint set is:

- `project_brief.md`: stable project goal, non-goals, constraints, key paths.
- `resume_brief.md`: current goal, locked acceptance, best result, latest
  diagnosis, next plan, and read-first artifact list.
- `current_hypothesis.md`: the current most credible explanation and next
  test.
- `failed_attempts.md`: directions that should not be repeated and why.

Recommended resume order:

1. `.metaloop/context/resume_brief.md`
2. `.metaloop/mission_capsule.json`
3. `.metaloop/verification_result.json`
4. `.metaloop/adaptive_loop.json`
5. `.metaloop/context/current_hypothesis.md`
6. `.metaloop/context/failed_attempts.md`
7. `.metaloop/event_log.jsonl`

## Kernel Commands

```bash
python3 "$KERNEL" --workspace . context init
python3 "$KERNEL" --workspace . context status --json
python3 "$KERNEL" --workspace . context read --file resume_brief.md
python3 "$KERNEL" --workspace . context write --file resume_brief.md --content "<markdown>"
```

The kernel only writes or reads Markdown checkpoints and appends audit events.
It does not summarize automatically, decide strategy, or modify locked
contracts.

## Discipline

Update `resume_brief.md` when:

- a long task reaches several attempts
- a major diagnosis changes
- a handoff to another agent/thread is expected
- context is becoming too large to reread safely
- the next plan depends on prior failed attempts

Keep the brief compact. If a new agent cannot recover the task in a few minutes
from the checkpoint plus locked artifacts, the checkpoint is too weak. If the
checkpoint becomes a full transcript, it is too large.

## Non-Goals

- No vector store
- No hidden memory
- No transcript archive
- No automatic summarizer in core
- No replacement for Mission Capsule, VerificationSpec, Adaptive Loop, or Event
  Log
