# MetaLoop Event-Triggered Outer-Loop Control Upgrade Proposal

Status: design proposal for the next v3.1-compatible iteration

Date: 2026-07-21

## 1. Executive Decision

MetaLoop should be treated as a minimal, orthogonal, event-triggered outer-loop
control system for Agent-driven work:

> Help a capable but stochastic, partially informed, and self-misjudging Agent
> converge toward locked user intent under uncertainty, while the user supplies
> command intent, handles true exceptions, and makes only reserved final
> decisions.

The Agent's inner loop remains responsible for understanding, designing,
editing, testing, and fixing. MetaLoop observes that work at meaningful control
points, evaluates deviation from the locked target, diagnoses failures, changes
the assurance level or next action, and repeats until the result is accepted or
stopped.

```text
inner loop:  understand -> design -> change -> test -> fix

outer loop:  observe -> evaluate -> diagnose -> adjust -> repeat
```

The outer loop must be mostly inactive when the inner loop is stable and the
claim is cheap to verify. It should increase control effort only when durability
risk, semantic uncertainty, irreversible impact, or conflicting feedback makes
additional observation valuable. This is gain scheduling, not ceremony.

This direction keeps the v3.1 low-friction routine path and restores automatic
independent feedback only for semantic high-risk work. A test failure, reviewer
follow-up, documentation synchronization, Contract correction, or exact Git
commit still does not create a new Task. Review is one additional Evaluation
authority in the same Task, not a parallel project-management workflow.

### 1.1 Control-System Identity

The conceptual mapping is:

| Control concept | MetaLoop realization |
| --- | --- |
| Setpoint / command intent | User goal locked in a ContractRevision |
| Controlled plant | The project, code, experiment, or artifact being changed |
| Controller / actuator | The capable Agent performing and adapting the work |
| Sensors | Git state, validators, tests, Evidence, and independent Review |
| Error signal | Evaluation against the locked acceptance target |
| State estimate | RecoveryView plus explicit observation and diagnosis |
| Control decision | `complete`, `continue`, `repair`, `redesign`, `pivot`, `stop`, or `escalate` |
| Supervisory commander | The user, who provides intent and resolves real exceptions |

MetaLoop is therefore not the Agent's brain, a scheduler, or a replacement for
engineering judgment. It is the small external structure that makes target,
observation, error, correction, and acceptance durable and auditable.

### 1.2 Kalman-Style Inspiration Without A Kalman Filter

Agent work is partially observable. The Agent sees only part of the project at
any moment; tests observe selected behavior; Git observes content identity but
not semantic correctness; self-reports are useful but correlated with the
implementation that produced them; reviewers add an independent but still
imperfect observation.

The useful lesson from state estimation is to combine several imperfect sensors
and spend more observation effort when uncertainty is high. MetaLoop does not
need covariance matrices, numerical filtering, or a simulated plant model. It
needs only disciplined distinctions between:

- measured workspace facts and Agent interpretation;
- mechanically decidable evidence and semantic judgment;
- known state, inferred state, and unresolved uncertainty;
- confidence sufficient for routine progress and uncertainty that triggers a
  stronger sensor such as independent Review.

### 1.3 Mission-Command Inspiration

The user should state the desired end state, boundaries, resources, prohibited
actions, and any decision they reserve. The Agent should then act autonomously
inside those constraints, adapting tactics from feedback without repeatedly
asking permission for ordinary repairs.

Escalation is appropriate only when intent is ambiguous in a way that changes
the target, constraints conflict, new authority or resources are required, an
irreversible decision was not delegated, or evidence leaves two materially
different acceptable outcomes. Protocol mechanics, retry choices, reviewer
follow-ups, and local implementation details remain the Agent's responsibility.

### 1.4 Minimality And Orthogonality

MetaLoop should preserve one primitive for each independent concern:

- Git for workspace-change truth;
- ContractRevision for locked intent and acceptance;
- Attempt for one strategy;
- Evidence and validators for observation;
- Evaluation/Review for error and authority;
- DecisionEvent for correction;
- RecoveryView for derived resumable state.

New behavior should compose these primitives rather than introduce a scheduler,
daemon, agent pool, transcript memory, project-specific semantic engine, second
task ontology, or duplicate source of truth. Every proposed record or command
must remove a demonstrated ambiguity that cannot be handled by the existing
orthogonal set.

## 2. Observed Gap

MetaLoop v3.1 correctly retains immutable verification, Review overlays, linear
authority, exact Evidence, and same-Task repair. Its optimization also correctly
removes routine reviewer and user authority. Current use nevertheless exposes
two opposite control defects.

First, low-risk work can be over-controlled. Merely working on MetaLoop or
following the Skill can lead the Agent to initialize protocol state, query
status, checkpoint, verify integrity, and manage lifecycle records for an
atomic change where Git and one project check are sufficient. The bookkeeping
then becomes a second task and weakens Agent focus.

Second, high-risk work can be under-observed:

1. reviewer authority is activated only when the Contract explicitly declares
   it;
2. `attempt finish` executes the declared contract but does not create or launch
   an independent reviewer;
3. the Worker currently decides whether semantic review is needed without a
   sufficiently explicit risk-classification discipline;
4. an under-classified task can therefore pass every locked mechanical validator
   and reach the user before any independent semantic review occurs.

In the second failure mode, MetaLoop still proves exactly which incomplete
validators passed. It does not falsely accept the Task when user authority is
pending, but the user becomes the first real semantic reviewer. That preserves
protocol truth while creating avoidable late rework.

The defect is not missing lifecycle or Review machinery. It is unreliable
activation and gain selection: too much control effort when uncertainty is low,
and too little independent sensing when semantic uncertainty is high.

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

## 5. Assurance Classification And Trigger Policy

The Agent selects the lowest tier that can defend the intended claim. This is a
control-policy decision, not a new kernel lifecycle. From Tier 1 upward, the
selected tier, reasons, and triggered rules belong in the ContractRevision.
Uncertainty promotes assurance; later evidence may reduce it once the unstable
condition is resolved.

### 5.1 Tier 0: `atomic_direct`

Use Git directly and create no MetaLoop protocol state when all of the following
hold:

- the change is atomic, local, reversible, and readily inspected;
- no independent resume or handoff is expected;
- no sealed semantic authority, external side effect, or reserved acceptance is
  involved;
- normal project validation is enough to defend the result.

Typical examples are a small documentation correction, formatting, or a narrow
mechanical edit. Tier 0 means zero MetaLoop kernel calls. Git remains the durable
change record.

Explicit invocation matters: when the user says to use `$metaloop`, the task is
at least Tier 1 because durable protocol control was requested. Merely
mentioning MetaLoop, inspecting its source, or editing MetaLoop's own docs does
not count as an invocation.

### 5.2 Tier 1: `durable_routine`

Use the ordinary durable path for non-trivial or independently resumable work
whose acceptance is predominantly mechanical:

```text
task begin -> inner-loop work -> attempt finish
```

Once the project is initialized, this tier should normally require only two
lifecycle writes. `task begin` locks intent and starts the Attempt; `attempt
finish` reconciles, checkpoints, seals, verifies, and accepts when no authority
is pending. Routine work must not require repeated status, checkpoint,
integrity, recover-write, or low-level lifecycle calls unless an actual event
requires them.

### 5.3 Tier 2: `governed`

Add managed Evidence, stronger validators, stable-input identities, or a
project-native conformance view when exact outputs or important cross-module
behavior must be defended. Typical examples include an internal API spanning
several owners, migrations with deterministic invariants, or artifacts whose
identity matters.

Tier 2 still need not use an independent reviewer when the complete obligation
is mechanically decidable. The Agent performs an adversarial self-check and
derives positive and negative tests from the governing contract rather than
only from its implementation.

### 5.4 Tier 3: `high_assurance`

Use independent reviewer authority when a hard trigger in Section 6 applies and
semantic correctness cannot be fully reduced to executable checks:

```text
durable continuity
  + executable proof
  + exact Evidence where identity matters
  + independent reviewer authority
  + user authority only when explicitly reserved
```

The reviewer must run before the result is presented to the user as acceptance
ready. User authority is optional and appears only for a decision the user
actually reserved; permission to proceed is not final acceptance authority.

### 5.5 Event-Triggered Gain Scheduling

Assurance changes in response to observable events:

| Observed condition | Outer-loop response |
| --- | --- |
| Stable, local, mechanically decidable work | Stay inactive at Tier 0 or use the Tier 1 fast path |
| Resume, handoff, task switching, or workspace-attribution risk | Activate Tier 1 durable state |
| Exact artifact identity or cross-module invariant matters | Raise to Tier 2 sensing and Evidence |
| Semantic uncertainty, correlated self-test blind spots, or irreversible impact | Raise to Tier 3 independent Review |
| Reviewer and implementation evidence conflict | Diagnose and retry in the same Task |
| Locked intent, evidence, and authority genuinely conflict | Escalate to the user |
| Verification becomes stable and the trigger is gone | Reduce control effort; do not retain ceremony by inertia |

A failing test alone does not raise the tier or create a Task. The relevant
event is what the failure reveals: an implementation defect leads to repair; a
defective contract or validator leads to a ContractRevision; unresolved
semantic uncertainty may require stronger observation.

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

The Worker owns assurance-tier selection and reviewer configuration. The user
is not asked to choose a tier, name an Evaluation, approve local repairs, or
operate the protocol. Explicit `$metaloop` invocation selects at least Tier 1;
the Agent raises assurance automatically when observable triggers require it.

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

1. Define Tier 0 through Tier 3 and require the Agent to select the lowest
   adequate tier during `Frame`.
2. Make explicit `$metaloop` invocation mean at least Tier 1 while preserving a
   zero-kernel Tier 0 for atomic direct work.
3. Add the event triggers and semantic hard triggers from this proposal.
4. Record tier rationale and triggered rules in Contract content from Tier 1
   upward.
5. Automatically add a manual reviewer validator for Tier 3 work.
6. Require a project-native conformance view before Tier 3 implementation.
7. Require a separate read-only reviewer agent after mechanical verification.
8. Keep reviewer repairs in the same Task and use the existing adaptive loop.
9. Do not present the result to the user until required reviewer authority is
   approved.
10. Require a structured reviewer report, using an interim DecisionEvent if
    necessary.
11. Tell the Agent to reduce assurance overhead after the triggering uncertainty
    is resolved rather than repeating lifecycle calls mechanically.

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

### 13.5 Concise CLI And Observation Surface

Routine commands should return a short default result containing only outcome,
blocker, pending authority, and next action. A `--full` option should expose
record identities, hashes, reconciliation, and diagnostic detail when needed.

Invalid enum-like input should name the legal values in the error. For example,
an invalid actor or authority role should not require source inspection to learn
that the accepted values are `worker`, `reviewer`, or `user` where applicable.

The Skill should not prescribe repeated `project integrity`, status,
checkpoint, or recovery writes for routine work. Integrity remains mandatory at
high-assurance closure and when alignment, recovery, or corruption is in doubt;
it is not a heartbeat command.

## 14. Rollout Plan

### Phase 1: Skill-Only Policy Trial

- add Tier 0 through Tier 3, event triggers, and hard triggers to `SKILL.md`;
- make the default Tier 1 lifecycle exactly `task begin` and `attempt finish`;
- add a Contract example for high-risk reviewer authority;
- use existing manual reviewer validators and `evaluate review`;
- store detailed review findings in a linked DecisionEvent;
- dogfood on atomic, durable-routine, governed, and high-assurance tasks.

Success means Tier 0 makes no kernel calls, Tier 1 normally makes two lifecycle
writes, and Tier 3 Tasks no longer reach the user before independent review.

### Phase 2: Review Report Support

- add structured review payload support to core and CLI;
- add backward-compatible tests over existing schema-version 3 databases;
- expose review report identity in status and integrity output;
- make default output concise and add `--full` diagnostics;
- improve invalid-value errors to list legal choices.

### Phase 3: Calibrate False Positives And False Negatives

- audit tasks classified Tier 0 through Tier 3;
- measure review frequency, review latency, blocking-finding rate, user-reported
  escaped findings, repair Attempts, protocol command count, and unnecessary
  user interruptions;
- narrow triggers that produce no useful findings;
- strengthen triggers associated with escaped semantic defects.

## 15. Falsifiable Acceptance Criteria For The Upgrade

1. An atomic direct documentation or formatting change uses Tier 0 and makes
   zero MetaLoop kernel calls.
2. An explicitly invoked, routine `$metaloop` task uses Tier 1 and normally
   requires only `task begin` and `attempt finish` as lifecycle writes.
3. A mechanically decidable local repair does not acquire reviewer or user
   authority merely because tests initially fail.
4. A Task changing a sealed interface's consumed source layer is Tier 3 and
   cannot become acceptance-ready without reviewer authority.
5. A Task changing ownership, reference, order, binding, or truncation semantics
   becomes Tier 3 unless complete mechanical decidability is demonstrated.
6. An approved mechanical Evaluation with pending reviewer authority is exposed
   as pending reviewer, not ready for user acceptance.
7. A reviewer `needs_changes` result leads to a new Attempt in the same Task,
   not a review or repair Task.
8. A reviewer report records concrete questions, counterexamples, findings,
   residual risks, and exact subject identity.
9. The Worker cannot satisfy independent reviewer authority with the same actor
   identity or agent context.
10. User authority appears only when the user explicitly reserves final
   acceptance.
11. Existing v3 databases, low-level commands, Git alignment, Evidence, and
    linear Evaluation-chain guarantees remain valid.
12. Routine-task median protocol operations do not regress materially from
    v3.1.
13. Default CLI output is short, `--full` exposes details, and invalid role or
    authority input lists legal values.
14. In a Tier 3 dogfood sample, escaped semantic findings discovered first by
    the user decrease relative to the current v3.1 policy.
15. After reviewer-requested repair restores stability, the same Task continues
    without a repair Task or repeated user authorization.

## 16. Recommended Decision

Adopt Phase 1 as a Skill-policy correction to v3.1, not as a reversal of the
v3.1 optimization.

The governing principle should be:

> Keep the outer loop dormant when the Agent's inner loop is stable. Activate
> only the smallest additional sensor and control action justified by observed
> uncertainty; require independent Review when semantic hard triggers make
> Worker-only verification insufficient; escalate to the user only for command
> intent, true exceptions, and reserved final decisions.

This keeps MetaLoop light where code can prove the claim, durable where work can
drift or be interrupted, and independently observable where the implementer and
its tests can share the same blind spot.
