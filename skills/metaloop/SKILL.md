---
name: metaloop
description: "Use when a Git project needs durable recovery across long sessions, task switching, carried-forward work, sealed completion evidence, or an independent review of a high-risk claim. Keep atomic local edits, routine tests, documentation sync, and reversible implementation work on Git plus project-native checks unless the user explicitly requests durable tracking."
---

# MetaLoop v3.4

Use MetaLoop as a quiet outer loop around Codex. Trust the Agent. Protect
against context loss, omission, ambiguous state, self-misjudgment, and shared
blind spots without turning protocol maintenance into the task.

Use the self-contained kernel:

```bash
KERNEL="<skill_dir>/scripts/metaloop_kernel.py"
```

Require a local Git repository and Python 3.12+. Do not require a remote,
GitHub, a clean worktree, host attestation, or an authenticated context ID.

## Keep The Work Primary

Apply this order:

1. Implement and run project-native checks.
2. Persist only state needed for recovery or exact completion.
3. Add independent Review only to the final claim that needs it.
4. Return to implementation immediately after feedback.

Treat assurance as completion policy, not as permission to work. Never make an
architecture implementation high assurance merely because it concerns
architecture. Judge the claim and its oracle.

## Route By Work And Claim

Choose the lowest sufficient route:

- `atomic_direct` (Tier 0): use Git plus project tests for local, reversible
  implementation, test repair, documentation sync, status work, and ordinary
  performance engineering. Create no MetaLoop Task.
- `durable_routine` (Tier 1): use one Task when implementation is non-trivial,
  resumable, or likely to cross context compaction. Keep the Agent-facing path
  to `task begin -> Work -> attempt finish`.
- `governed` (Tier 2): add stable inputs, managed outputs, artifact hashes, or
  stronger validators when the whole completion claim is mechanically
  decidable.
- `high_assurance` (Tier 3): add a fresh-context structured Review only for
  security/privacy or information-leakage risk, irreversible production or
  external effects, causal/domain semantics with an incomplete executable
  oracle, contract correctness that cannot be mechanically decided, or a
  formal experiment/paper/benchmark claim.

Do not trigger Review because code spans modules, changes a schema, modifies
architecture, was written with its tests, or performs ordinary optimization.
Those are risk signals, not independent-review requirements.

Explicit `$metaloop` means at least Tier 1 unless the user is asking about or
editing MetaLoop itself without requesting durable tracking.

## Use Two Lifecycle Commands

Initialize once when no v3 Project exists:

```bash
python3 "$KERNEL" --workspace . project init
```

Start resumable implementation:

```bash
python3 "$KERNEL" --workspace . task begin \
  --title "<goal>" \
  --plan "<implementation plan>" \
  --check "<project-native verifier>"
```

Implement first. Run normal project tools directly. Then use the single closure
entry:

```bash
python3 "$KERNEL" --workspace . attempt finish --attempt <attempt_id>
```

`task begin` atomically creates the Task, minimal ContractRevision, selection,
and Attempt. Invalid input leaves no empty Task.

`attempt finish` must do the routine protocol work:

- reconcile every workspace change made after the Attempt baseline;
- treat explicit `--deferred-path` and `--assigned-path` as exceptions;
- bind only declared managed outputs or explicit artifacts as Evidence;
- checkpoint, seal, and run locked mechanical validators;
- accept when no authority remains;
- otherwise return the exact next transition;
- resume from existing checkpoint, Evidence, sealed Attempt, or Evaluation when
  the same command is repeated.

Do not pass every source path through `--claimed-path`. Calling `finish` is
the Agent's normal confirmation that changes since the baseline belong to the
current Attempt. Keep explicit path classification for true exclusions or
conflicts.

## Carry Work Forward Automatically

When the latest same-Task Attempt is aborted, rejected, or superseded and the
workspace is non-conflicted, start the next Attempt normally. Let the kernel
adopt the current workspace as its baseline and record:

- source Attempt, Contract, status, execution hash, and checkpoint hash;
- source and adopted WorkspaceStamp hashes;
- each carried path with source and adopted state.

The carried set spans the source Attempt baseline, its latest checkpoint, and
the adopted workspace. Reject adoption before Attempt creation when any carried
path falls outside the current Contract scope.

Do not reverse and reapply patches merely to satisfy Attempt timing. Do not ask
the user to enumerate inherited files. Use `--retry-of` only to override an
ambiguous source; the default source is the latest terminal Attempt in the same
Task.

Never adopt `conflicted` or `unknown` workspace state. Branch switches,
resets, unsafe HEAD changes, cross-Task sources, and paths outside the Contract
scope still require explicit correction.

## Observe Only On Events

Use `observe --format brief` or `recover show` only after resume, context
compaction, Task switching, or a state discrepancy. RecoveryView is derived
from SQLite plus live Git and does not require a write.

Read integrity precisely:

- `valid`: protocol content and the applicable workspace claim are intact;
- `not_yet_reconciled`: an active Attempt has ordinary `ahead` work to finish;
- `violated`: identity, hash, Evidence, stable input, conflict, or closed-claim
  invariants failed.

Use the derived `active_chain` instead of expanding superseded Tasks, Attempts,
or Evaluation branches during normal recovery.

Record a semantic checkpoint only before handoff/compaction or after a
meaningful decision that cannot be derived from Git and tests. Never write
checkpoints as progress heartbeats.

Use the control projection literally:

```text
verify -> review:reviewer -> review:user -> accept
failure or non-approved Review -> start_repair_attempt
```

Keep validator repair, Review follow-up, Contract correction, and retries in
the same Task.

## Review The Claim, Not The Work Log

Run project validators before Review. For Tier 3, bind one structured report to
the active mechanical Evaluation. Include:

```text
review_scope
questions_and_findings
counterexamples_executed
blocking_findings
nonblocking_risks
resolved_trigger_ids
decision
```

Use reviewer authority for delegatable semantic judgment. Use user authority
only when the user explicitly reserves the final decision. Context labels are
optional diagnostics and never acceptance gates.

When `attempt finish` or recovery returns `review:reviewer`, pass its derived
`review_handoff` to the fresh reviewer. It already binds the current claim,
trigger focus, validator summary, paths, Evidence, active chain, and empty
report template. Do not build a second packet workflow or persist the handoff;
the completed Review Evaluation remains the authority.

After `needs_changes`, implement the repair in a new Attempt under the same
Task and run `attempt finish` again. Create a ContractRevision only when the
goal, scope, acceptance, authority, or assurance actually changed.

## Maintain A Protocol Budget

Budget routine durable work for two Agent-facing lifecycle commands: one
`begin` and one resumable `finish`. Read the derived `protocol_activity`
and `routing_warning`; do not add state writes merely to measure activity.

If the host can measure active work time, warn when MetaLoop interaction
exceeds 10% of task time. Treat the warning as a routing signal, never an
acceptance gate. If no host timing exists, use command count, repeated Attempts,
and excess checkpoints as proxies.

When a routine Task needs repeated low-level commands, fix or resume
`attempt finish` instead of teaching the Agent more ceremony.

## Reject These Anti-Patterns

- Do not create a high-assurance Task before ordinary implementation.
- Do not bind every changed source or test file as Evidence.
- Do not use checkpoint, status, integrity, or recovery writes as heartbeats.
- Do not create Git changes solely to satisfy protocol state.
- Do not create a Task because a test, validator, Review, or format field failed.
- Do not create clean-head promotion Tasks for exact commits.
- Do not make the user maintain IDs, CAS versions, authorities, or internal
  recovery state.
- Do not use Review for formatting, documentation sync, test repair, routine
  performance work, or mechanically decidable claims.
- Do not descend into low-level commands while resumable `finish` can perform
  or continue the transition.

## Use Low-Level Commands Only For Real Exceptions

Use explicit `task contract`, `attempt record-checkpoint`, `attempt
evidence`, `attempt seal`, and `evaluate *` only for progressive design,
multiple strategies, explicit exclusions, managed formal artifacts, external
authority, or protocol diagnosis. Keep them out of the routine workflow.

Use one Task unless a branch has independent ownership, acceptance, resources,
or stopping conditions. Use separate Git worktrees for parallel mutating
Attempts.

For an external training run or long process, optionally record one recovery
locator and checkpoint identity through `--external-ref` and
`--external-checkpoint-identity`. Treat it as non-authoritative navigation.
Read epochs, liveness, metrics, and completion from the external system's own
manifest; MetaLoop never monitors or schedules the run.

## Preserve Truth Boundaries

```text
Prompt handles intelligence.
Git handles workspace-change truth.
SQLite handles protocol-state truth.
Project documents handle architecture-content truth.
Project validators and Review handle completion truth.
```

Use `Frame -> Work -> Reconcile -> Adapt -> Prove` as a reasoning model, not a
mandatory command sequence. Let the inner loop run while stable; activate the
outer loop only on recovery, ownership, verification, semantic-claim, or
authority events.

Keep these guarantees:

- no unacknowledged WorkspaceStamp passes acceptance;
- only the active Evaluation head passes acceptance;
- a declared high-assurance trigger cannot disappear silently;
- Recovery projects one legal next transition;
- observation does not mutate real Git index, objects, refs, or locks.

Do not build a scheduler, daemon, transcript store, vector memory, agent pool,
project manager, second Task ontology, or project-specific technical oracle.

## References

- Read `references/final_protocol.md` when implementing or diagnosing kernel
  lifecycle behavior.
- Read `references/prompt_first_code_backed.md` when deciding whether logic
  belongs in prompts, Git, SQLite, or deterministic code.
