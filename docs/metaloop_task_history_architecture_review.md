# MetaLoop Task History Architecture Review

Date: 2026-07-20
Status: Accepted and implemented as the MetaLoop v2 architecture decision

## Purpose

This note evaluates whether MetaLoop can evolve from one-workspace/one-current-
mission governance into a compact, recoverable project-history protocol that
supports:

- several tasks progressing in one project or Codex session;
- a large task composed from smaller work units;
- repair branches that return to their parent task;
- context compaction, thread replacement, and handoff;
- reconstruction of decisions, attempts, evidence, and current state without
  treating chat history as operational truth.

The desired implementation style is minimal, orthogonal, inspectable, and
skill-first. This document intentionally separates repository observations
from architectural recommendations so that red-team and blue-team reviewers
can challenge the proposal without inheriting its conclusions.

## Executive Assessment

MetaLoop's product direction is strong: Skill-only, prompt-first/code-backed,
locked Mission Capsules, independent verification, compact context recovery,
and no hidden agent runtime. The current implementation is capability-rich,
but its state semantics have not yet converged around a durable unit of work.

The original recommendation was to introduce one canonical Task identity. An
adversarial review accepted that direction but found that identity alone does
not protect evidence or recovery. The revised recommendation is:

> Build MetaLoop v2 around an immutable, content-bound evidence
> chain from ContractRevision to Attempt to Evaluation to Review. Task owns
> scope and lifecycle; a freshness-checked Recovery Head makes that chain
> resumable. Use SQLite as canonical operational state and generate inspectable
> JSON/Markdown projections from it.

The architecture is implemented. Further changes should be driven by real
trial evidence rather than additional speculative framework design.

## Final Architecture Decision

The implemented product model is:

```text
Codex intelligence
  -> self-contained $metaloop Skill
  -> thin portable kernel
  -> canonical vendored metaloop_core
  -> .metaloop/metaloop.db
  -> Project / Task / ContractRevision / Attempt / Evaluation / DecisionEvent
  -> freshness-checked RecoveryView and rebuildable projections
```

SQLite was selected because the required correctness properties are relational
and transactional: foreign-key identity, one-open-Attempt uniqueness, Task
compare-and-swap, monotonic event cursors, exact Evaluation subject binding,
and atomic Task/Event transitions. Large evidence remains on the filesystem
and is referenced by path and hash.

The file-tree design remains useful as an export/projection format, but it is
not canonical state. Root compatibility artifacts remain supported in
v1-only workspaces and as legacy import; they become read-only after v2
initialization and cannot grant v2 authority unless content validation plus a
fresh validator rerun proves the exact execution binding.

## Repository Observations

The following are direct observations from the current repository, not design
preferences.

### 1. Workspace is the current state namespace

`WorkspacePaths` resolves one current copy of each major artifact:

```text
.metaloop/mission_capsule.json
.metaloop/execution_report.json
.metaloop/verification_result.json
.metaloop/adaptive_loop.json
.metaloop/observation_report.json
.metaloop/diagnosis_report.json
```

This is a coherent single-mission design. It does not natively retain several
independent active tasks or multiple immutable execution/verification attempts
inside one workspace.

### 2. There is no canonical task or attempt identity

The current protocol contains several local identities:

```text
capsule_id
loop_id
iteration_id
job_id
node_id
thread_id
observation_id
diagnosis_id
event_id
```

The implementation does not currently define canonical fields such as:

```text
task_id
parent_task_id
active_task_id
attempt_id
depends_on
return_to_task_id
spawned_by_event_id
```

Consequently, artifacts can be correlated by workspace, capsule, timestamps,
or convention, but not through one end-to-end work-unit identity.

### 3. Feedback facts have overlapping representations

An observation, diagnosis, decision, or next plan may appear in several
places:

- an Adaptive Goal Loop iteration;
- `observation_report.json` and `diagnosis_report.json`;
- `event_log.jsonl`;
- `current_hypothesis.md` and `failed_attempts.md`;
- `resume_brief.md`;
- thread registry notes.

These surfaces serve different readers, but their authority and synchronization
rules are not fully explicit when their contents disagree.

### 4. History is only partially immutable

Mission Capsule revisions are archived. Current execution, verification,
review, adaptive, observation, and diagnosis artifacts are workspace-level
files and are not uniformly archived per attempt. The event log preserves
selected history, but events do not carry task ID, attempt ID, contract
revision, or source revision as canonical fields.

### 5. Portable kernel and reusable core duplicated protocol behavior

At the time of this review:

```text
skills/metaloop/scripts/metaloop_kernel.py   3,523 lines
src/metaloop_core/*.py                       3,472 lines
```

The portable kernel was deliberately self-contained, and parity tests covered
important behavior, but adversarial review found actual drift in thread and
context Capsule binding. V2 resolves this by making `src/metaloop_core/`
canonical, generating a vendored Skill copy, and reducing the script to a thin
bootstrap adapter. V1 compatibility code is frozen and receives correctness
fixes only.

### 6. MetaLoop does not yet fully dogfood context recovery

The repository's own `.metaloop/context/` checkpoint set was absent during
this review, although the current Mission Capsule had reached revision 11.
The thread registry still referenced the first capsule ID, and the current
structured status did not fully reflect reviewer evidence recorded in the
event log. These are useful product signals: the protocol currently relies on
agents maintaining several independent artifacts correctly.

### 7. Existing boundaries remain valuable

The following boundaries are coherent and should not be discarded casually:

- Skill-only product surface;
- prompt handles intelligence, code handles truth;
- Mission Capsule and VerificationSpec are locked completion contracts;
- worker self-report is not verification;
- reviewer authority is distinct from worker authority;
- context checkpoints are recovery notes, not transcripts or hidden memory;
- dashboard/observation is read-only;
- control files express intent rather than silently mutating contracts;
- routing, relay, and activation are bounded one-shot operations rather than a
  scheduler or daemon.

### 8. Current reviews are not bound to executions

The current `ReviewResult` binds Capsule identity/revision and
VerificationSpec hash, but not ExecutionReport identity or content. A
counterexample constructed during adversarial review demonstrated:

```text
execute A -> review approved -> completed_verified
execute B overwrites ExecutionReport
verify again -> completed_verified using the old review
```

This is a correctness boundary, not merely a history feature. An approval for
one execution must never authorize a different execution, even when both use
the same Capsule and VerificationSpec.

### 9. Current context health does not prove recovery freshness

`context_summary()` currently reports file existence, size, and mtime. It
cannot determine whether a present `resume_brief.md` covers the latest
Contract, Attempt, Evaluation, or decision. A stale but non-empty checkpoint
therefore appears healthy.

## Proposed Minimal Algebra

The revised model has six authoritative concepts and one derived recovery
concept.

### Authoritative concepts

| Concept | Responsibility |
|---|---|
| Project | Project identity and default UI/recovery task pointer |
| Task | Recoverable, pausable, branchable unit of work |
| ContractRevision | Immutable goal, rationale, non-goals, constraints, and VerificationSpec |
| Attempt | One execution bound to one ContractRevision; immutable after seal |
| Evaluation | Append-only judgment of one immutable subject |
| DecisionEvent | Append-only observation, diagnosis, decision, or next-plan record |

### Derived concept

| Concept | Responsibility |
|---|---|
| RecoveryView | Source-bound Recovery Head plus a human-readable resume projection |

The intended orthogonality is:

```text
Task             answers what unit of work exists and which immutable heads are current.
ContractRevision answers what success and boundaries mean for that task.
Attempt          answers what was executed under which exact contract.
Evaluation       answers what evaluator judged which exact immutable subject.
DecisionEvent    answers what observation or decision was recorded and why.
RecoveryView     answers what a new agent should read now and whether it is fresh.
```

### Reference integrity

Every authoritative reference should carry an ID and a content hash. The
minimum chain is:

```text
ContractRevision
  -> Attempt(task_ref, contract_ref, attempt_id, execution_hash)
  -> Evaluation(attempt_ref, verification_spec_hash, evaluator identity/version)
  -> Review(subject_evaluation_ref, reviewer identity/role)
```

Review is a specialized authority judgment over a specific Evaluation, not a
floating approval for the current workspace. Verification must traverse the
complete reference chain and fail closed on any ID/hash mismatch.

One Attempt may have several immutable Evaluations and Reviews. New records
append; they do not overwrite old judgments.

### Field-level authority

The authority rules are:

- `ContractRevision` is immutable after lock.
- `Task` is authoritative for current lifecycle, dependency state, and head
  references.
- `Attempt` and `Evaluation` are immutable after seal/write.
- `DecisionEvent` proves that an observation, diagnosis, or decision was
  recorded; it does not independently set current Task state.
- `RecoveryView` and all other projections are never valid write sources and
  may be deleted and rebuilt.

Task transitions and their audit events should be written atomically. If a
projection conflicts with authoritative records, the projection is stale.

Mission Capsule maps to immutable ContractRevision content. Mutable
`current_status` and `status_history` must move out of the locked Capsule and
into Task lifecycle state.

## Mapping Existing Concepts

The proposal does not require discarding the existing vocabulary. It gives
each existing artifact one role:

```text
Mission Capsule       -> ContractRevision
ExecutionReport       -> sealed Attempt record
VerificationResult    -> Evaluation of an AttemptRef
ReviewResult          -> Evaluation/authority decision over an EvaluationRef
Adaptive Goal Loop    -> DecisionEvent/history projection
Observation/Diagnosis -> typed DecisionEvent payload or derived projection
Context checkpoint    -> source-bound RecoveryView
Thread registry       -> Task assignment projection/default scope
Job envelope          -> Cross-workspace Task handoff format
Observe/dashboard     -> Read-only projection
Control request       -> External intent event
Activation            -> Optional adapter that acts on explicit ready state
```

The important constraint is that Job, Capsule, Loop, and Node should not each
become a competing task ontology. A handoff may have a transport ID, but it
should refer to one canonical `task_id`.

## Logical Records Before Storage

The protocol should define records and invariants before selecting a directory
tree or SQLite. The minimum logical Task head is:

```text
task_id
parent_task_id
spawned_by_event_id
depends_on
status
state_version
contract_head_ref
latest_attempt_refs
latest_evaluation_refs
latest_decision_event_id
```

`return_to_task_id` is intentionally excluded. Returning to a parent or prior
task is session/interface navigation, not Task-domain truth. A child Task may
provide evidence or unblock a dependency; it must not automatically complete
its parent.

The Project record may contain `default_task_id` for UI and recovery
convenience. It must not be an implicit execution scope.

### Recovery Head

The machine-checkable Recovery Head should bind at least:

```text
task_id
task_state_version
contract_head_ref
latest_attempt_refs
latest_evaluation_refs
latest_decision_event_id
projection_source_hash
generated_at
```

The human-readable `resume.md` remains agent-authored, but status must classify
the pair as `fresh`, `stale`, or `incomplete` by comparing Recovery Head source
references with current Task heads.

A new session should read a bounded set: Task head, Contract head, Recovery
Head, resume projection, latest Attempt/Evaluation records, and only events
newer than the Recovery Head watermark.

### Canonical storage

SQLite is canonical operational state, with transactions, foreign keys,
uniqueness constraints, monotonic cursors, schema migration, and JSON/Markdown
projections. The protocol invariants remain tested through the service API,
not through ad hoc SQL assumptions.

The immutable file tree is implemented as `.metaloop/v2/` export projections.
Root compatibility files may exist only as source-marked caches, projections,
or v1 migration input; their mutable commands fail closed once v2 exists, so
they cannot become a second source of truth.

## Explicit Execution Scope

`default_task_id` is a UI/recovery default. Mutating operations must resolve to
explicit immutable subjects:

```text
run       -> task_id + contract_ref, creates attempt_id
verify    -> task_id + attempt_id
review    -> task_id + evaluation_id
event     -> task_id, optionally attempt_id
context   -> task_id + Recovery Head
```

When several runnable Tasks or reviewable Attempts exist and no unambiguous
scope is supplied, commands must fail closed. Thread assignment may supply a
default, but an explicit command binding always wins.

Existing root-level artifacts may remain as read-only migration inputs. The
implementation does not dual-write active Task state back into those paths.

## Branch and Composition Semantics

The model should distinguish three cases.

### Work units inside one acceptance contract

Small implementation steps that only compose one final acceptance target do
not automatically need child Tasks. They may remain planned actions or
checklist items inside one Task.

### Repair branch

A discovered defect becomes a child Task only when it needs independent state,
evidence, pause/resume behavior, or responsibility. It records its parent and
originating event. Completion may unblock the parent or contribute evidence;
interface navigation decides what the session resumes next.

### Independent task

A task with independent acceptance, lifecycle, ownership, or stopping
condition receives its own Task identity even when it shares the same Git
workspace or Codex session.

This avoids both extremes: one giant mission that loses local history and a
task object for every trivial action.

## Portable Distribution Recommendation

The self-contained Skill requirement does not require a hand-maintained
single-file implementation.

A candidate distribution model is:

```text
src/metaloop_core/                    canonical implementation
          -> release/build sync
skills/metaloop/lib/metaloop_core/    vendored generated copy
skills/metaloop/scripts/metaloop_kernel.py
                                      thin argument and presentation adapter
```

Alternatives include a generated single-file bundle or stdlib zipapp. The
architectural requirement is one source of protocol semantics, not one source
file. Generated-package identity and behavior should be checked in CI.

## Implemented Sequence

The implementation followed this risk-controlled sequence:

1. Freeze new routing, activation, and dashboard features temporarily.
2. Fix the current review boundary: bind ExecutionReport identity/hash through
   VerificationResult and ReviewResult, and add the regression test that an
   old review cannot approve a new execution.
3. Establish one canonical protocol implementation and generated/vendored
   Skill distribution before expanding the schema further.
4. Specify v2 reference, immutability, authority, recovery-freshness, and
   explicit-scope invariants independently of storage.
5. Add `task_id`, `attempt_id`, and strict cross-references to current root
   artifacts without moving storage yet.
6. Add immutable Attempt/Evaluation history and freshness-checked Recovery
   Heads.
7. Add Task switching, parent/child relations, and dependency edges.
8. Select SQLite canonical storage and retain file-tree output as projections.
9. Migrate thread, control, routing, relay, activation, dashboard, and root
   compatibility projections onto canonical Task/Attempt references.
10. Add executable coverage for paused/multiple Tasks, repair dependencies,
    open Attempt recovery, stale projections, duplicate replay, CAS conflicts,
    review binding, artifact mutation, and legacy migration.

## Red-Team Questions

Reviewers arguing against the proposal should test at least these claims:

1. Is Task genuinely the missing primitive, or can multiple active missions be
   represented more simply by separate workspaces?
2. Does task-scoped storage turn a lightweight protocol into a project
   management system?
3. Is append-only history necessary, or are Git plus current-state artifacts
   sufficient?
4. Are Adaptive, Feedback, Event, and Context actually redundant, or do they
   carry distinct authority that should remain independently stored?
5. Would vendoring `metaloop_core` inside the Skill make deployment, debugging,
   or trust worse than the current single-file kernel?
6. Are routing and activation real user needs, or evidence of architecture
   expanding ahead of validated demand?
7. Can hooks reliably maintain task history without recreating an agent
   runtime?
8. What is the smallest counterexample where the proposed algebra fails?
9. Does SQLite materially improve correctness under expected concurrency, or
   merely hide a protocol that is still underspecified?
10. Can Recovery Head freshness be derived without creating another mutable
    truth source?

## Blue-Team Questions

Reviewers defending or refining the proposal should demonstrate:

1. A new session can recover two paused tasks and one repair branch without
   reading chat history.
2. An agent cannot confuse evidence from one attempt or contract revision with
   another.
3. Completed and failed attempts remain inspectable after switching tasks.
4. Existing single-task usage remains nearly unchanged for the user.
5. The model does not require a scheduler, daemon, vector store, or hidden
   memory.
6. Root-level backward compatibility can be maintained during migration.
7. The number of authoritative concepts and synchronization rules decreases,
   rather than merely moving complexity into new directories.
8. Portable Skill behavior comes from one canonical implementation.
9. A previously approved Review cannot authorize a new or modified Attempt.
10. A stale resume projection is detected without reading the full event log.

## Decision Criteria

The implementation is accepted only while executable tests continue to show
all of the following:

- recovery after context compaction is materially better;
- duplicate or stale task execution is easier to detect;
- independent task and attempt evidence cannot be accidentally mixed;
- every Review resolves to one immutable Evaluation and one immutable Attempt;
- changing ExecutionReport content invalidates all unrelated prior approval;
- RecoveryView freshness is mechanically classified as fresh, stale, or
  incomplete;
- concurrent writers cannot silently act through a shared active-task pointer;
- single-task workflows retain low ceremony;
- authoritative state locations decrease or become clearer;
- no hidden scheduler or autonomous runtime is introduced;
- portable Skill installation remains self-contained;
- migration preserves existing verified artifacts or provides an explicit
  compatibility reader;
- implementation complexity is justified by real multi-task use cases.

The proposal should be rejected or redesigned if it mainly adds files,
commands, IDs, and lifecycle states without reducing ambiguity or improving
recovery.

## Current Bottom Line

### Adversarial hardening result

An independent red-team pass after the first implementation found that a
nominally content-bound graph was still insufficient at its operational
boundaries. The implementation now treats the following as required parts of
the architecture rather than incidental checks:

- live Attempt evidence is rehashed at seal, verification, and acceptance;
  default-Task workspace drift is visible through project integrity;
- every blocking reviewer/user authority is persisted and must appear in one
  approved linear chain;
- DecisionEvent Attempt/Evaluation references must exist and remain inside the
  event Task, with database and integrity backstops;
- v1 migration validates content hashes, reruns locked validators, and commits
  atomically; unverifiable history is always `legacy_unbound`;
- v1 mutable artifacts fail closed after v2 initialization, except explicit
  external control intent, so compatibility cannot become competing truth;
- RecoveryView retains bounded supersession-resolved Project/Task decisions,
  binds dependency heads, exposes the acceptance chain, and uses compact
  payload/manifest summaries with explicit detail commands;
- repair origin, dependency removal, event history, and thread assignments are
  inspectable protocol surfaces;
- cancelled Tasks cannot be revived, while repeated acceptance of the same
  head is idempotent;
- a valid terminal chain derives `ready_to_accept`, preventing the UI/agent
  from starting a redundant Attempt after verification already passed.

These counterexamples sharpen the central rule: immutable database references
prove historical identity, while acceptance also needs current evidence and
recovery needs durable present-tense decisions. Neither property can be
inferred from the other.

MetaLoop v2 is now a durable work protocol rather than a single-current-Mission
workspace. Immutable reference integrity, explicit execution scope, Task CAS,
exact replay detection, and a freshness-checked Recovery Head make multiple
Tasks recoverable without creating a scheduler or second memory system.

The next product phase is real use. Architecture changes should now answer
observed failures in recovery quality, Attempt boundaries, fingerprint utility,
Task-switch ergonomics, or concurrent writer behavior. This document records
the decision; executable invariants remain implementation authority.
