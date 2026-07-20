# MetaLoop v3.1 Alpha Optimization Spec

Status: implementation contract

Date: 2026-07-20

## 1. Problem

Alpha use shows that MetaLoop v3 prevents false acceptance on architecture,
research-boundary, inventory, reviewer, and user-authority work. The same use
also shows that routine work pays the full governance cost:

- explicit Task, Contract, Recovery, Attempt, Evidence, Evaluation, and
  acceptance commands for small changes;
- promotion Tasks after ordinary Git commits change `HEAD`;
- new Tasks where a failed validator, reviewer follow-up, or defective
  ContractRevision should remain inside the same Task;
- reviewer and user authority applied to mechanical work rather than semantic
  claims.

The architectural defect is not the durable graph. It is that assurance cost
is not proportional to the claim being made.

## 2. Goal

Make MetaLoop a low-friction durable development protocol by default while
preserving the exact Evidence, Evaluation, Review, and authority guarantees
needed for high-risk work.

The canonical ontology remains:

```text
Project -> Task -> ContractRevision -> Attempt -> Evaluation
                                    -> Evidence
                                    -> DecisionEvent
RecoveryView is derived from canonical state and live Git state.
```

There is no second fast-mode database, lifecycle, Task type, or acceptance
truth.

## 3. Invariants

1. SQLite remains protocol-state truth.
2. Git remains workspace-change truth.
3. No unacknowledged workspace content may pass acceptance.
4. A content-preserving Git commit must not require a new Task.
5. Branch switches, resets, amended history, dirty post-commit state, or tree
   mismatch remain conflicted.
6. RecoveryView is derived; a hand-written resume note is optional metadata,
   not a freshness prerequisite.
7. ContractRevision, sealed Attempt, Evidence, and Evaluation remain immutable
   and content-bound.
8. User permission to continue is not user acceptance of a result.
9. Reviewer authority is required only when the Contract explicitly declares
   semantic review.
10. Existing schema-version 3 databases remain readable without migration or
    authority loss.

## 4. Proportional Assurance

Assurance obligations are additive rather than separate operating modes:

```text
continuity
  + executable proof when the claim is mechanically testable
  + exact Evidence when outputs are contract-managed
  + independent authority only when explicitly reserved
```

Routine changes use one Task for one independently resumable goal and one
Attempt for one strategy. Test failures, reviewer follow-ups, documentation
sync, Contract corrections, and Git commits do not create Tasks by themselves.

- Implementation failure: new Attempt under the same ContractRevision.
- Defective goal, scope, validator, or authority: new ContractRevision in the
  same Task, then a new Attempt.
- Independent ownership, acceptance, or stopping conditions: child Task.

## 5. Derived Recovery

`recover show` computes its source and live alignment on every read. It is
`fresh` whenever that computation succeeds and alignment is `aligned`, whether
or not a resume note has been written.

`recover write` stores only an optional resume annotation. It does not create
authority and is not required before Attempt start.

## 6. Content-Preserving Commit Promotion

WorkspaceStamp adds:

- `head_tree_digest`: the tree owned by current `HEAD`;
- `head_parent_oids`: direct parents of current `HEAD`;
- `materialized_tree_digest`: the Git tree produced by the complete current
  worktree using an isolated temporary index, without mutating the real index
  or worktree.

A changed `HEAD` is treated as aligned only when all conditions hold:

1. repository and worktree identity are unchanged;
2. the previous `HEAD` is a direct parent of the current `HEAD`;
3. the previous materialized tree equals the current `HEAD` tree;
4. the current index equals the current `HEAD` tree;
5. the current worktree has no uncommitted or untracked changes;
6. stable inputs and Evidence still pass their existing live checks.

This is a content-preserving promotion, not new implementation work. Any
missing proof fails closed. Old WorkspaceStamp records without a materialized
tree continue to use strict v3 conflict semantics until a new checkpoint is
recorded.

## 7. Low-Friction Commands

The low-level commands remain available. Two orchestration commands compose
the same durable methods and write no second truth:

### `task begin`

Creates one Task, locks its ContractRevision, selects it, and starts its first
Attempt. Derived Recovery removes the separate recovery-write step.

### `attempt finish`

For one explicit open Attempt:

1. records one checkpoint when a delta exists, using explicit path
   classifications;
2. automatically attaches exact Evidence for declared managed outputs;
3. seals the Attempt;
4. runs locked validators;
5. accepts automatically only when verification is approved and no external
   authority is required;
6. otherwise returns the immutable Evaluation and pending authority.

Declared managed outputs may be claimed automatically because ownership was
already locked in the Contract. Other changed paths still require explicit
claim/defer/assign classification.

Partial completion remains durable. A rejected validator does not create a new
Task and an authority requirement does not get bypassed.

## 8. Skill Policy

The Skill must make the lowest adequate assurance path the default:

- no new Task for a commit, test failure, reviewer changes, documentation sync,
  or local repair under the same acceptance target;
- no reviewer for formatting, state synchronization, targeted tests, or other
  mechanically decidable claims;
- no user authority unless the user explicitly reserves final acceptance;
- no explicit Recovery write except when a resume annotation adds information
  not already derivable from canonical state;
- keep one Attempt open across local checkpoints until strategy, Contract, or
  immutable proof subject changes;
- use full governance for architecture, research conclusions, data boundaries,
  irreversible operations, and formal acceptance.

## 9. Acceptance Criteria

1. A Task can start without `recover write` and Recovery is fresh while aligned.
2. A direct commit of the exact checkpointed materialized tree remains aligned
   without a promotion Task.
3. A commit containing extra content, a branch/reset/amend, or a dirty
   post-commit worktree remains conflicted or ahead.
4. A routine CLI task can execute through `task begin`, one edit, and
   `attempt finish` without Review.
5. Managed outputs receive exact Evidence automatically during finish.
6. Explicit reviewer/user authority still blocks automatic acceptance.
7. Failed verification remains in the same Task and returns an immutable
   rejected Evaluation.
8. Existing low-level commands and schema-version 3 databases remain valid.
9. Canonical source and installed Skill core remain byte-identical.
10. Full tests, import boundary, surface audit, installed Skill parity, and
    `git diff --check` pass.

## 10. Non-Goals

- No daemon, watcher, scheduler, transcript store, vector memory, agent pool,
  project manager, or semantic keyword router.
- No automatic ownership inference from filenames or prose.
- No weakened Evidence, stable-input, Review, or user-authority checks.
- No automatic commit, push, branch switch, reset, or history rewrite.
- No schema reset and no import of archived V1/V2 authority.
