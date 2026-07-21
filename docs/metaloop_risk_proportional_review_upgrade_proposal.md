# MetaLoop Risk-Proportional Review Upgrade Proposal

Status: design proposal for the next v3.1-compatible iteration

Date: 2026-07-21

## 1. Executive Decision

MetaLoop should keep the v3.1 low-friction routine path and restore an automatic
independent feedback loop only for semantic high-risk work.

The intended behavior is:

```text
low risk     -> Worker -> executable verification -> accept when authority permits
medium risk  -> Worker -> adversarial self-check -> executable verification
high risk    -> Worker -> executable verification -> independent Review -> user if reserved
```

This is not a return to v2-style ceremony. A test failure, reviewer follow-up,
documentation synchronization, Contract correction, or exact Git commit still
does not create a new Task. Review is one additional Evaluation authority in the
same Task and is required only when the task's semantic risk justifies it.

## 2. Observed Gap

MetaLoop v3.1 correctly retains immutable verification, Review overlays, linear
authority, exact Evidence, and same-Task repair. Its optimization also correctly
removes routine reviewer and user authority.

The remaining gap is between those two properties:

1. reviewer authority is activated only when the Contract explicitly declares
   it;
2. `attempt finish` executes the declared contract but does not create or launch
   an independent reviewer;
3. the Worker currently decides whether semantic review is needed without a
   sufficiently explicit risk-classification discipline;
4. an under-classified task can therefore pass every locked mechanical validator
   and reach the user before any independent semantic review occurs.

In that failure mode, MetaLoop still proves exactly which incomplete validators
passed. It does not falsely accept the Task when user authority is pending, but
the user becomes the first real semantic reviewer. That preserves protocol
truth while creating avoidable late rework.

The defect is not the absence of Review machinery. The defect is unreliable
selection and configuration of that machinery.

## 3. Goals

1. Let the implementing Agent classify task risk without asking the user to
   understand MetaLoop terminology.
2. Make reviewer selection predictable through explicit hard triggers rather
   than an unstructured feeling that a task is "complex."
3. Require one independent semantic review for genuinely high-risk work before
   the result is presented as ready for user acceptance.
4. Keep repairs, reviewer follow-ups, and retries inside the same business Task.
5. Preserve the routine `task begin -> Work -> attempt finish` path.
6. Keep semantic intelligence in the Skill and project contracts rather than
   building a project-specific semantic engine in MetaLoop core.
7. Make reviewer findings auditable and useful, not a one-word `approved` record.

## 4. Non-Goals

- Do not review every commit, validator failure, targeted test, documentation
  update, or local implementation repair.
- Do not create a permanent agent pool, scheduler, daemon, or second task
  ontology.
- Do not hard-code compiler, research, security, database, or product-specific
  semantics into MetaLoop core.
- Do not ask the user to choose a risk tier or manually request a reviewer for
  an ordinary `$metaloop` invocation.
- Do not claim that independent review guarantees defect-free software.
- Do not weaken the current Git alignment, Evidence, stable-input, or authority
  checks.

## 5. Risk Classification

The Worker performs risk classification during `Frame`, before locking the
ContractRevision. The classification is recorded with reasons and the triggered
rules. Uncertainty promotes the task by one tier; it never silently lowers it.

### 5.1 Low Risk

Typical properties:

- formatting, prose clarification, generated index synchronization;
- local renaming with mechanically checked references;
- a narrow defect with a complete deterministic reproducer;
- no change to externally consumed behavior, authority, data interpretation, or
  irreversible state.

Required assurance:

```text
continuity + executable proof when applicable
```

Independent Review is not required.

### 5.2 Medium Risk

Typical properties:

- ordinary product behavior or an internal API changes;
- several modules participate, but ownership and acceptance remain explicit;
- compatibility and negative behavior are mechanically expressible;
- failure is reversible and does not alter a sealed semantic authority.

Required assurance:

```text
continuity + executable proof + Worker adversarial self-check
```

Review may be batched once per coherent work package. It should not run for
every checkpoint or repair.

### 5.3 High Risk

A task is high risk when any hard trigger below applies. The Worker must add
reviewer authority to the Contract unless an explicit, auditable rationale
proves that the trigger is fully mechanically decidable. Merely having many
tests is not such a rationale.

Required assurance:

```text
continuity
  + executable proof
  + exact Evidence where identity matters
  + independent reviewer authority
  + user authority only when explicitly reserved
```

## 6. High-Risk Hard Triggers

The following triggers are semantic categories, not a filename-only router.
Paths may provide evidence for a trigger, but the Worker must assess planned
behavior and actual information flow.

### 6.1 Authority And Contract Triggers

- creating, revising, superseding, or implementing against a sealed Contract,
  schema, manifest, protocol, claim ladder, or authority closure;
- changing behavior in a way that may exceed an existing `allowed_layers`,
  `input_kinds`, ownership boundary, prerequisite set, or public contract;
- interpreting an immutable artifact as compatible with behavior it did not
  authorize;
- changing formal acceptance, evidence identity, reviewer scope, or publication
  claims.

### 6.2 Semantic Data-Flow Triggers

- changing which data enters a model, decision, security boundary, evaluator,
  migration, or externally visible result;
- changing ownership, reference, ordering, binding, membership, lifecycle,
  truncation, missingness, or provenance semantics;
- changing a cross-module information path where a downstream consumer could
  bypass an upstream filter, validator, authorization, or accounting step;
- adding a new semantic object kind or source layer to an existing operator.

### 6.3 Irreversibility And Exposure Triggers

- destructive migrations, deletion, irreversible external writes, credentials,
  access control, privacy, security, billing, or production rollout;
- training or evaluation protocols that can consume a holdout, leak labels, or
  alter an evidence claim;
- any result whose failure would be costly to repair after publication,
  deployment, or user acceptance.

### 6.4 Verification-Limit Triggers

- important correctness depends on domain judgment not captured by executable
  validators;
- the Worker authored both the semantic interpretation and all tests that
  supposedly prove it;
- passing tests demonstrate examples but not the full relation, role, state
  space, or compatibility boundary.

## 7. Mandatory High-Risk Preflight

Before implementation, the Worker creates a compact conformance view inside the
project's normal design or evidence artifacts. MetaLoop must not impose one
domain-specific schema, but the view must answer:

```text
obligation
  -> governing authority
  -> actual planned input/source layer
  -> semantic precondition
  -> success postcondition
  -> forbidden behavior
  -> positive witness
  -> adversarial or negative witness
  -> executable validator or reviewer question
```

For an operator-oriented project this may be an operator conformance matrix. For
a migration it may be a field and invariant matrix. For a security change it may
be a trust-boundary table.

The important rule is that tests are derived from the governing obligations,
not only from the implementation or the last reviewer finding.

If preflight discovers that planned behavior exceeds a sealed authority, the
Worker must create the appropriate versioned erratum, extension, or redesigned
Contract before implementation. Preserving the old artifact hash while silently
exceeding its semantics is not compatibility.

## 8. Review Policy

### 8.1 Independence

The semantic reviewer must not be the Worker that produced the Attempt. A
read-only reviewer may inspect the same aligned worktree because it does not
mutate it. Any repair returns to the Worker in a new Attempt.

The current kernel already rejects a reviewer identity equal to the original
Attempt actor. The Skill should additionally require a separate agent context
for high-risk review so independence is substantive rather than a renamed
self-review.

### 8.2 Reviewer Inputs

The reviewer receives:

- the exact ContractRevision and sealed Attempt identity;
- governing stable inputs and managed Evidence;
- the conformance view produced during preflight;
- the exact diff or committed tree;
- executable verification results;
- explicit claim and non-goal boundaries.

The reviewer should not rely only on the Worker's completion summary.

### 8.3 Reviewer Questions

At minimum, the reviewer answers:

1. Does actual behavior satisfy every governing semantic obligation?
2. Did the implementation consume any source, layer, object kind, authority, or
   dependency not admitted by the locked interface?
3. Are role-specific rules tested, rather than only generic type validity?
4. Can truncation, missing data, alternate order, reverse direction,
   incomparability, or stale identity bypass an upstream contract?
5. Do negative tests cover the defect class rather than only known examples?
6. Are the evidence and claim boundaries still honest?
7. What residual risks remain outside the current acceptance target?

### 8.4 Reviewer Output

A review must contain more than an identity and decision. Its structured report
should include:

```text
review_scope
governing_artifact_hashes
questions_and_findings
counterexamples_executed
blocking_findings
nonblocking_risks
decision
exact_evaluation_subject
```

Until the kernel supports a structured review payload, the Skill can record this
report as a content-bound DecisionEvent referring to the verification
`evaluation_id`, followed by the existing `evaluate review` command. A later
kernel enhancement should bind the report directly into the Review Evaluation.

## 9. Same-Task Feedback Loop

High-risk review does not require a review Task or a repair Task by default.

```text
Task
  ContractRevision
    Attempt 1
      checkpoint -> Evidence -> seal -> mechanical Evaluation
        independent Review: needs_changes
    DecisionEvent: diagnosis + repair plan
    Attempt 2
      checkpoint -> Evidence -> seal -> mechanical Evaluation
        independent Review: approved
        optional user Review: approved
  accept
```

Use a new ContractRevision only if the reviewer finds a defect in goal, scope,
acceptance, validator, authority, or execution scope. Use a new Task only when
ownership, acceptance target, or stopping conditions are genuinely independent.

This preserves durable feedback without turning review follow-up into project
management overhead.

## 10. User Interaction

The user should still be able to say:

```text
Use $metaloop. I want to <goal>.
```

The Worker owns risk classification and reviewer configuration. The user is not
asked to choose `low`, `medium`, or `high`, name an Evaluation, or approve local
repairs.

For high-risk work, the user sees only:

1. any genuinely blocking product or authority decision at Frame time;
2. the final result after mechanical verification and independent review;
3. residual risks and the exact acceptance subject when user authority was
   explicitly reserved.

Statuses must remain plain and precise:

```text
working
mechanically_verified_pending_reviewer
review_needs_changes
reviewed_ready_for_user_acceptance
accepted
```

`mechanical Evaluation: approved` must not be presented as
`ready_for_user_acceptance` while reviewer authority remains unsatisfied.

## 11. Proposed Skill Changes

The first upgrade should be primarily a Skill-policy change:

1. Add mandatory risk classification during `Frame`.
2. Add the hard triggers from this proposal.
3. Require a recorded rationale and triggered-rule list in the Contract content.
4. Automatically add a manual reviewer validator for high-risk work.
5. Require a project-native conformance view before high-risk implementation.
6. Require a separate read-only reviewer agent after mechanical verification.
7. Keep reviewer repairs in the same Task and use the existing adaptive loop.
8. Do not present the result to the user until reviewer authority is approved.
9. Require a structured reviewer report, using an interim DecisionEvent if
   necessary.

These changes need no new database ontology and can initially preserve schema
version 3.

## 12. Proposed Project-Validator Responsibilities

MetaLoop cannot know domain semantics such as whether one event must precede
another. The target project should validate what can be made executable:

- actual input/source layers against admitted interface layers;
- dependency and prerequisite closure;
- ownership and reference resolution;
- information-flow isolation and truncation accounting;
- artifact and authority identities;
- generated positive and adversarial fixtures;
- forbidden imports, paths, fields, claims, or side effects.

MetaLoop binds those validators into the Contract and proves which exact
Attempt they evaluated. It does not replace them.

## 13. Optional Kernel Enhancements

Kernel changes are useful but not required for the first policy rollout.

### 13.1 Structured Review Payload

Extend `evaluate review` with an optional `--report-file` or `--payload-json`.
Store the normalized report in the Review Evaluation content and hash. Existing
minimal reviews remain readable.

### 13.2 Assurance Observation

Expose the Contract-declared risk tier, trigger list, and pending reviewer in
`project status` and RecoveryView. Treat these as declared protocol facts, not
kernel-inferred semantics.

### 13.3 Acceptance-Readiness Wording

Return a derived readiness label that distinguishes mechanical approval from
authority-complete acceptance. Do not add a second lifecycle state machine.

### 13.4 Reviewer Agent Hook

If the host supports agent delegation, the Skill or host may invoke a read-only
reviewer after an approved mechanical Evaluation. The kernel should remain an
authority and integrity engine, not an agent scheduler.

## 14. Rollout Plan

### Phase 1: Skill-Only Policy Trial

- add the risk classifier and hard triggers to `SKILL.md`;
- add a Contract example for high-risk reviewer authority;
- use existing manual reviewer validators and `evaluate review`;
- store detailed review findings in a linked DecisionEvent;
- dogfood on several routine and high-risk tasks.

Success means routine command count does not increase while high-risk Tasks no
longer reach the user before independent review.

### Phase 2: Review Report Support

- add structured review payload support to core and CLI;
- add backward-compatible tests over existing schema-version 3 databases;
- expose review report identity in status and integrity output.

### Phase 3: Calibrate False Positives And False Negatives

- audit tasks classified low, medium, and high;
- measure review frequency, review latency, blocking-finding rate, user-reported
  escaped findings, repair Attempts, and protocol command count;
- narrow triggers that produce no useful findings;
- strengthen triggers associated with escaped semantic defects.

## 15. Falsifiable Acceptance Criteria For The Upgrade

1. A formatting-only Task still completes through `task begin`, one edit, and
   `attempt finish` without Review.
2. A mechanically decidable local repair does not acquire reviewer or user
   authority merely because tests initially fail.
3. A Task changing a sealed interface's consumed source layer is classified
   high risk and cannot become acceptance-ready without reviewer authority.
4. A Task changing ownership, reference, order, binding, or truncation semantics
   is classified high risk.
5. An approved mechanical Evaluation with pending reviewer authority is exposed
   as pending reviewer, not ready for user acceptance.
6. A reviewer `needs_changes` result leads to a new Attempt in the same Task,
   not a review or repair Task.
7. A reviewer report records concrete questions, counterexamples, findings,
   residual risks, and exact subject identity.
8. The Worker cannot satisfy independent reviewer authority with the same actor
   identity or agent context.
9. User authority appears only when the user explicitly reserves final
   acceptance.
10. Existing v3 databases, low-level commands, Git alignment, Evidence, and
    linear Evaluation-chain guarantees remain valid.
11. Routine-task median protocol operations do not regress materially from
    v3.1.
12. In a high-risk dogfood sample, escaped semantic findings discovered first by
    the user decrease relative to the current v3.1 policy.

## 16. Recommended Decision

Adopt Phase 1 as a Skill-policy correction to v3.1, not as a reversal of the
v3.1 optimization.

The governing principle should be:

> Default to no Review for routine work. Require one independent Review when
> explicit semantic hard triggers make Worker-only verification insufficient.

This keeps MetaLoop light where code can prove the claim and restores the
feedback loop where the implementer and its tests can share the same blind
spot.
