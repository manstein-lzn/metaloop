---
name: metaloop
description: "Use when a Git project task needs risk-proportional durable history, recovery across long sessions, task switching, explicit reconciliation, structured verification, or high-assurance review."
---

# MetaLoop v3.2

MetaLoop is a minimal, orthogonal, event-triggered outer-loop control system.
It uses a durable goal, current state, corrective feedback, and independent
observation only when needed so a capable but stochastic and locally limited
Agent keeps converging on the user's locked target. The user supplies intent,
true exceptions, and explicitly reserved final decisions.

Trust the Agent as cooperative. MetaLoop handles context loss, omission,
self-misjudgment, ambiguous state, and correlated blind spots; it is not a
zero-trust security boundary around the Agent. Admit a mechanism only when it
materially reduces omission or ambiguity, supplies actionable feedback, or
reduces user burden without disproportionate protocol cost.

This Skill is self-contained. Use `scripts/metaloop_kernel.py`; do not assume a
separate package or command is installed.

## Operating Contract

```text
Prompt handles intelligence.
Git handles workspace-change truth.
SQLite handles protocol-state truth.
Project documents handle architecture-content truth.
Validators and Review handle completion truth.
```

The portable kernel is a thin bootstrap over vendored `metaloop_core`. JSON and
Markdown under `.metaloop/` are rebuildable projections. They are never a
second write authority.

MetaLoop requires a local Git repository and Python 3.12+ with standard-library
SQLite. It does not require a remote repository or clean worktree.

## User Burden

The user should be able to say only:

```text
Use $metaloop. I want to <goal>.
```

Do not require the user to name internal records or commands. Infer the
smallest adequate protocol shape and ask only questions that change the target,
acceptance, cost, permissions, destructive risk, data access, or external
resources.

## First Response And Tier Selection

Select the lowest tier that can defend the intended claim. Explicit `$metaloop`
invocation means at least Tier 1. Tier 0 makes no kernel calls. For Tier 1 and
above:

1. Inspect `project status` and the selected Task RecoveryView when initialized.
2. Read README, STATE, HANDOFF, and only the project files needed for scope,
   acceptance, risk, and evidence.
3. Stop inspection when more searching no longer changes the design or
   verification plan.
4. State the goal, success evidence, non-goals, constraints, risks, and stopping
   conditions in proportion to the task.
5. Record the tier, trigger IDs, rationale, and authorities in the immutable
   ContractRevision.
6. Use one Task unless independent ownership, acceptance, or stopping conditions
   require a graph.

If the repository has no v3 Project, initialize it. If a non-v3 database is
present, stop and require an explicit clean-cut archive/reinitialization; do not
load old authority into the final protocol.

## Frame, Work, Reconcile, Adapt, Prove

### Frame

Perform bounded inspection and proportionate design. Lock one ContractRevision
containing goal, rationale, constraints, non-goals, acceptance criteria,
VerificationSpec, protocol shape, and optional execution scope.

### Work

Start one Attempt for one strategy under one exact ContractRevision. Record
semantic checkpoints after meaningful progress and before context compaction,
handoff, or Task switching.

### Reconcile

Git changes after the latest checkpoint make the workspace `ahead`. Explicitly
classify every changed path before writing the next checkpoint:

- `claim`: belongs to the current Attempt;
- `defer`: intentionally excluded, with a reason;
- `assign`: belongs to another explicit Task;
- `conflict`: attribution is unsafe; stop and resolve.

MetaLoop never guesses ownership from filenames or prose.

A direct Git commit may remain aligned when Git proves it is only a
content-preserving promotion of the exact checkpointed worktree tree. Extra
content, dirty post-commit state, branch switches, resets, and amended history
remain conflicted.

### Adapt

After failed or partial verification, record observation, diagnosis, an
explicit decision, and the next plan before retrying. Code validates the
vocabulary but never infers repair, redesign, or pivot from keywords.

### Prove

Checkpoint the current WorkspaceStamp, attach exact Evidence, seal the Attempt,
run locked validators, satisfy required Review/user authorities, and accept the
exact Evaluation chain. Any unacknowledged workspace state fails closed.

## Six Gates

1. `Design Gate`: clarify outcome, boundaries, evidence, and stopping conditions.
2. `State Checkpoint`: persist semantic progress and a code-computed WorkspaceStamp.
3. `Verification Gate`: let locked validators and evidence decide completion.
4. `Adaptive Loop`: diagnose failed or partial work before retrying.
5. `Control Point`: honor explicit external halt/resource/revision intent at safe points.
6. `Observation Surface`: expose read-only status, blockers, and next action.

## Progressive Design

Use Progressive Design for architecture and long-horizon work, not as ceremony
for every edit:

- derive a coherent target model and surface missing dimensions, risks, and choices;
- separate durable invariants from the current implementation slice;
- assign cohesive module ownership and explicit interfaces;
- record deliberate concessions and the evidence that should revisit them;
- prefer a representative project-native walking skeleton;
- advance only when current evidence justifies the next slice.

Each design response should add a deduction, risk, choice, or clearer structure.
A one-line repair should remain proportionate.

## Event-Triggered Assurance

Assurance tiers are additive Contract policy, not separate lifecycles:

0. `atomic_direct`: use Git directly for an atomic, local, reversible change
   that needs no independent resume, sealed semantic authority, external side
   effect, or reserved acceptance. Create no MetaLoop state.
1. `durable_routine`: use `task begin -> Work -> attempt finish` for non-trivial
   or resumable work whose acceptance is mechanically decidable.
2. `governed`: add stronger validators, stable inputs, managed Evidence, or a
   project-native conformance view when cross-module or exact artifact claims
   remain mechanically decidable.
3. `high_assurance`: add a fresh-context reviewer when a hard trigger applies
   and semantic correctness cannot be completely reduced to executable checks.

Use Tier 3 unconditionally for security, privacy, production impact,
irreversible external effects, or formal evidence leakage. Use Tier 3
conditionally for a semantic change with an incomplete executable oracle. A
cross-module, schema, protocol, or formal-contract change remains Tier 2 when
its complete obligation is mechanically decidable. Treat uncertainty about
applicability as a reason to promote. The Worker authoring both code and tests is
a correlation signal, not a Tier 3 trigger by itself.

Raise assurance when observed events justify it. Once Tier 3 records unresolved
trigger IDs, keep it sticky for the current acceptance target. Lower it only in
a new ContractRevision that names every resolved trigger, explains the
resolution, and binds an approved Evaluation from the prior ContractRevision.
Require a normalized proof for every trigger: either a passing executable
validator with stable `validator_id` and explicit `resolves_trigger_ids`, or a
host-verified structured reviewer Evaluation whose report names the trigger.
Ordinary passing tests, unmapped Evidence, manual validators, and unverified
Review do not resolve triggers. This preserves risk memory across compaction; it
does not express distrust.

Do not retain ceremony after the relevant uncertainty is resolved. A failed
test alone means repair or Contract correction, not automatic tier promotion or
a new Task.

## ContractRevision

ContractRevision is the only task contract. It is immutable and contains no
mutable lifecycle status. New contracts include a normalized `assurance` block:

```json
{
  "tier": "durable_routine | governed | high_assurance",
  "trigger_ids": [],
  "rationale": [],
  "required_authorities": [],
  "resolved_trigger_ids": [],
  "resolution_evaluation_id": null
}
```

The kernel always derives reviewer authority for `high_assurance`; Contract
input may add authority but cannot remove the derived requirement. Existing v3
Contract v1.0 records remain readable in legacy mode. Architecture-sensitive
work may also include `execution_scope`:

- `paths`: declared scope, never sandbox enforcement;
- `stable_inputs`: project documents whose hashes must not drift;
- `managed_outputs`: files that must become exact Attempt Evidence;
- `change_kind`: explicit `repair`, `extension`, or `redesign`;
- `migration_plan`: a locked stable input required for redesign.

Project design prose stays in project documents; the Contract stores only
roles, paths, hashes, and scope declarations.

When an executable validator resolves assurance uncertainty, declare the
mapping in the locked validator itself:

```json
{"validator_id": "stable_oracle_id", "resolves_trigger_ids": ["trigger_id"]}
```

Keep validator IDs unique within a Contract. Never attach trigger resolution to
a manual validator.

## Git Workspace Contract

Every Project records repository root, worktree path, and adapter version.
Every Attempt records an immutable baseline WorkspaceStamp. Each checkpoint
records the current stamp and semantic reconciliation.

Workspace alignment is exactly one of:

- `aligned`: live Git state equals the latest checkpoint;
- `ahead`: project content changed after the checkpoint;
- `conflicted`: worktree identity, HEAD, merge state, or attribution is unsafe;
- `unknown`: Git or bounded observation failed.

WorkspaceStamp records the current `HEAD` tree, its direct parents, and an exact
materialized worktree tree computed through a repository-external temporary Git
index and object directory. The real object store is read only through an
alternate, and observation uses `GIT_OPTIONAL_LOCKS=0`. A new direct commit is
aligned only when its tree equals the previous materialized tree and the live
index/worktree are clean.

Recovery is fresh only when its SQLite sources are current and workspace
alignment is `aligned`. `ahead`, `conflicted`, and `unknown` block lifecycle
completion until explicitly resolved.

One worktree permits one open mutating Attempt. Parallel mutating work requires
separate Git worktrees and therefore separate Project identities.

## Primary Commands

Set the kernel path relative to this Skill:

```bash
KERNEL="<skill_dir>/scripts/metaloop_kernel.py"
```

Initialize once, only when the repository has no v3 Project:

```bash
python3 "$KERNEL" --workspace . project init
```

Routine workflow:

```bash
python3 "$KERNEL" --workspace . task begin --title "<task>" --contract contract.json --plan "<plan>"
# Work
python3 "$KERNEL" --workspace . attempt finish --attempt <attempt_id> --claimed-path <path>
```

`task begin` composes create, contract, select, and Attempt start. `attempt
finish` checkpoints explicit path classifications, binds declared managed
outputs as Evidence, seals, verifies, and accepts only when no external
authority is pending. Both write the same canonical records as the low-level
commands. Routine Tier 1 work normally performs exactly these two lifecycle
writes; do not use status, integrity, checkpoint, or recovery writes as
heartbeats.

Use `observe --format brief` or `recover show` only on resume, Task switch,
context uncertainty, or an observed state discrepancy. Use `project integrity`
for high-assurance closure or suspected corruption, not as a routine command.

Use low-level `task create/contract`, `attempt start/record-checkpoint/evidence/
seal`, and `evaluate verify/review/accept` when progressive design, multiple
Attempts, failed verification, or external authority needs explicit control.
`recover write` is optional resume annotation, never a start prerequisite.

Use `task decision`, `task depend`, `task assign`, `task return`, and Task
transitions for explicit branching, dependencies, persistent-thread focus, and
pause/resume. A child Task may unblock or provide evidence to a parent but
never completes the parent implicitly.

## Task and Attempt Boundaries

Use one Task for one independently resumable goal. Create a child only when the
branch needs its own contract, evidence, lifecycle, ownership, or stopping
conditions. Small steps sharing one acceptance target remain checkpoints in one
Attempt.

Never create a Task solely because:

- a validator or test failed;
- a reviewer requested changes;
- a Contract validator or scope needs correction;
- documentation or state needs synchronization;
- the exact checkpointed content was committed to Git.

Implementation failure starts a new Attempt under the same ContractRevision.
A defective goal, scope, validator, or authority creates a new ContractRevision
in the same Task. A commit is a workspace transition, not implementation work.

One Attempt is one strategy under one exact ContractRevision. Exact replay of a
sealed or aborted Attempt requires a concrete retry reason. Semantic similarity
remains Agent judgment.

Before expensive work, the derived RecoveryView must be fresh. It is computed
from canonical SQLite and live Git state and does not require a prior write.
Before handoff, Task switch, or likely context compaction, checkpoint meaningful
progress. Write a resume annotation only when it adds non-derivable context.

## Verification and Authority

Worker self-report is not evidence. Verification creates an immutable
Evaluation over one sealed Attempt hash. Review is another Evaluation over the
previous Evaluation hash. `acceptance_head_id` is the one active Evaluation
head for the Task: Review must extend it, a new Attempt supersedes it, and
acceptance cannot select an older sibling or stale chain.

Follow the kernel's ordered transition exactly:

```text
verify -> review:reviewer -> review:user -> accept
failure or non-approved Review -> start_repair_attempt
```

Reviewer authority always precedes a reserved user decision. Do not append a
Review after a non-approved Review or after all authority is satisfied. Use the
typed `next_transition` projection as the executable protocol action; malformed
historical chains remain immutable and recover through a new Attempt.

Use executable validators proportionate to the claim: commands, metrics,
schemas, artifact hashes, non-regression checks, and forbidden paths. Use
reviewer authority for delegatable judgment and user authority only when the
user explicitly reserves it.

Permission to continue routine work is not acceptance authority. Record bounded
standing permission as a DecisionEvent when useful, but do not add a manual
user-acceptance validator unless the user reserved approval of the result.
Reviewer authority is for semantic claims and conclusions, not formatting,
status updates, or mechanically decidable checks.

For Tier 3, use a reviewer in a fresh Agent context after mechanical
verification. Let the host integration set `METALOOP_HOST_CONTEXT_ID` and
optionally `METALOOP_HOST_CONTEXT_PROVIDER`. The CLI `--context-id` flag is a
manual label and is always stored as `manual / unverified`; it cannot prove
fresh-context independence. The purpose is to decorrelate reasoning, not to
authenticate against a hostile Agent. If the host cannot attest distinct
contexts, continue development through a repair Attempt but do not complete
Tier 3 acceptance; involve the user only when a real exception is required.

Tier 3 `evaluate review` requires `--report-file` or `--report-json`. The report
contains:

```text
review_scope
questions_and_findings
counterexamples_executed
blocking_findings
nonblocking_risks
resolved_trigger_ids
decision
```

The kernel adds exact Contract, Attempt, Evidence, and parent Evaluation hashes,
then binds the normalized report into the Review Evaluation content hash. An
approved report cannot contain blocking findings. Reviewer-requested repair
starts a new Attempt in the same Task; create a new ContractRevision only when
goal, scope, verification, authority, or assurance changed.

Use these readiness meanings precisely:

- `working`: an Attempt is active;
- `mechanically_verified_pending_reviewer`: validators passed but reviewer
  authority is still pending;
- `review_needs_changes`: diagnose and retry in the same Task;
- `evaluation_chain_invalid`: preserve history and start a repair Attempt;
- `high_assurance_review_unverified`: continue through a repair Attempt, but do
  not accept the Tier 3 claim;
- `reviewed_ready_for_user_acceptance`: only an explicitly reserved user
  decision remains;
- `acceptance_ready`: all proof and authority are satisfied;
- `accepted`: the active head was accepted.

Evidence, stable inputs, immutable record hashes, Git identity, and workspace
alignment are rechecked at seal, verify, review, accept, and integrity. Do not
start another Attempt when an approved chain is ready to accept.

## Adaptive Decisions

Use only explicit values:

- `complete`: locked success is satisfied;
- `continue`: another high-signal attempt is justified;
- `repair`: implementation is defective while the contract remains correct;
- `redesign`: goal, scope, acceptance, authority, or contract is defective;
- `pivot`: retain the goal but change strategy;
- `stop`: continuing is not useful;
- `escalate`: permissions, policy, resources, or reserved authority block work.

## Host and Guarantee Boundary

The optional `metaloop_core.host.safe_point` function is a synchronous read/check
adapter for hosts that expose turn, compaction, or tool-batch hooks. It is not a
daemon, watcher, scheduler, or Agent brain.

The portable guarantees are precise:

```text
No unacknowledged WorkspaceStamp may pass acceptance.
Only the active Evaluation head may pass acceptance.
Declared high assurance cannot silently lose its unresolved trigger memory.
Recovery projects one ordered, CAS-protected next transition.
```

The kernel guarantees execution of declared assurance; semantic trigger
classification remains Skill, host-policy, and project-validator judgment. The
Skill cannot control an Agent that bypasses every protocol entry. Divergence is
discovered at the next explicit command or optional host safe point.

## Hard Boundaries

- SQLite is the only mutable protocol-state authority.
- Git is workspace-change truth, not semantic or completion truth.
- ContractRevision, sealed Attempt, Evidence, DecisionEvent, and Evaluation are
  content-bound.
- Structured Review findings are part of the Review Evaluation, never an
  unbound DecisionEvent sidecar.
- RecoveryView is derived and never a write authority.
- `default_task_id` and thread assignment are navigation only.
- Declared paths are not permission enforcement.
- Do not build a second task ontology, hidden runtime, scheduler, vector memory,
  transcript store, project manager, or project-specific policy in core.

## References

- `references/final_protocol.md`: v3 record, lifecycle, and alignment semantics.
- `references/prompt_first_code_backed.md`: intelligence and truth boundaries.
