# Mission Capsule Constitution

Last updated: 2026-05-03

## Status

This document is the constitutional architecture reference for MetaLoop.

It defines the durable mission object, its lifecycle, authority rules, evidence semantics, and relationship to ITC, SCP, SKS, AMP, Codex, and MetaLoop.

Implementation documents may simplify this model for the current release, but they must not violate the invariants in this document.

## Core Thesis

MetaLoop is not a chat-history wrapper and not a second coding agent.

MetaLoop is a local-first mission governance system:

```text
User Intent
  -> Co-Design
  -> Mission Capsule
  -> Contract Compilation
  -> Codex Execution
  -> Evidence Ledger
  -> MetaLoop Verification
  -> Route / Repair / Redesign / Decompose / Close
```

The central durable object is the **Mission Capsule**.

Codex executes. MetaLoop governs.

## Layer Model

The architecture has one product primitive and several supporting layers.

```text
Mission Capsule
  = durable task container and contract of record

ITC
  = Intent Transmission Contract
  = role/invocation contract compiled from the Capsule

SCP
  = Structured Context Protocol
  = context compiler that turns Capsule + ITC + refs into minimal LLM input

SKS
  = Structured Knowledge System
  = reference, provenance, freshness, and permission substrate

AMP
  = Agent Message Protocol
  = structured events, reports, requests, decisions, and state updates

Codex
  = execution engine

MetaLoop
  = mission governance, verification, routing, audit, and closure
```

Important rule:

```text
Mission Capsule is canonical.
ITC, SCP, SKS, AMP are support layers.
```

Do not create a second universal protocol that competes with the Capsule. Universal intent transmission is the umbrella idea; Mission Capsule is the concrete durable object.

## Mission Capsule Definition

A Mission Capsule is the durable governance object for one mission.

It is not a prompt. It is not a transcript. It is not just a run log.

It binds:

- intent
- scope
- authority
- domain obligations
- acceptance criteria
- evidence requirements
- references and provenance
- execution attempts
- decisions
- lifecycle state
- closure outcome

A future reviewer should be able to inspect a Capsule and reconstruct:

- what was authorized
- what was forbidden
- what was attempted
- what evidence was produced
- what was accepted or rejected
- why the terminal outcome was reached

This is the future-reader test.

## Capsule Contents

### Core Capsule v1

The canonical v1 Capsule should be small:

```text
MissionCapsule
  identity
  mission_charter
  authority_contract
  acceptance_contract
  domain_profile_id
  reference_set
  evidence_ledger
  attempt_history
  decision_ledger
  lifecycle_state
  closure_outcome
```

### Identity

Identity records:

- `capsule_id`
- `capsule_version`
- `created_at`
- `created_by`
- `owner`
- optional `parent_capsule_id`
- optional `child_capsule_ids`

Every Capsule must have durable identity.

### Mission Charter

The Mission Charter records:

- user intent
- desired outcome
- explicit non-goals
- scope boundaries
- known constraints
- urgency or priority when relevant
- domain profile binding

After authorization, intent and acceptance-relevant scope become locked.

### Authority Contract

The Authority Contract records:

- who authorized the mission
- what files, tools, commands, networks, external systems, and side effects are allowed
- what requires approval
- what is forbidden
- spending, time, and resource limits
- whether decomposition is allowed
- what authority can be delegated to child Capsules

Permissions cannot expand implicitly.

If a run needs more authority, the Capsule must transition to a blocked or redesign state and record the authority update.

### Acceptance Contract

The Acceptance Contract records:

- acceptance criteria
- admissible evidence classes for each criterion
- hard validators
- soft review criteria
- final human acceptance criteria
- required artifacts
- required evidence
- accepted limitations, if any
- whether partial acceptance is allowed

The executor may not weaken acceptance criteria.

### Domain Profile Binding

A DomainProfile is a normative modifier.

It is not a label.

It defines domain-specific obligations for:

- artifact types
- validators
- evidence
- source policy
- risk policy
- repair strategy
- decomposition strategy
- audit requirements

The active DomainProfile is pinned per authorized Capsule version.

### Reference Set

The Reference Set records:

- user-provided references
- discovered references
- authoritative sources
- assumptions
- exclusions
- freshness requirements
- source provenance

References are appendable. They are not silently overwritten.

If a reference is superseded, stale, contradicted, or invalidated, record that as a new fact.

### Evidence Ledger

The Evidence Ledger records evidence used to justify:

- verification
- acceptance
- rejection
- repair
- redesign
- decomposition
- blocking
- closure

Evidence is append-only.

Evidence can be invalidated, contradicted, superseded, or marked stale. It should not be deleted from the audit record.

### Attempt History

Attempt History records coherent execution attempts.

Each AttemptRecord is tied to:

- Capsule version
- executor
- context snapshot
- active permissions
- references used
- actions taken
- artifacts produced
- evidence produced
- outcome
- failure mode
- lessons
- staleness markers

Attempt history is append-only.

Historical attempts are advisory unless revalidated against the current Capsule.

### Decision Ledger

The Decision Ledger records:

- major design choices
- alternatives considered
- user decisions
- reviewer decisions
- repair decisions
- redesign decisions
- decomposition decisions
- waivers
- closure decisions

Decision records should cite evidence.

## Lifecycle State And Closure Outcome

State and outcome must be separated.

Lifecycle state answers:

```text
Where is the Capsule in the process?
```

Closure outcome answers:

```text
How did this Capsule end?
```

### Lifecycle States v1

Use this lean lifecycle for v1:

```text
Draft
Proposed
Authorized
InProgress
Blocked
ReviewReady
Repairing
RedesignRequired
WaitingOnChildren
Closed
Archived
```

### Closure Outcomes v1

Use closure outcomes separately:

```text
accepted
accepted_with_limitations
accepted_pending_human
rejected
cancelled
decomposed
failed
superseded
```

`Archived` is a retention state, not an acceptance outcome.

`Rejected` is an outcome or review result, not a general-purpose process state.

### Legal Transitions v1

Recommended legal transitions:

```text
Draft
  -> Proposed
  -> Closed(cancelled)

Proposed
  -> Draft
  -> Authorized
  -> Closed(cancelled)

Authorized
  -> InProgress
  -> Blocked
  -> Closed(cancelled)

InProgress
  -> ReviewReady
  -> Blocked
  -> Repairing
  -> RedesignRequired
  -> WaitingOnChildren
  -> Closed(cancelled|failed|superseded)

Blocked
  -> Authorized
  -> InProgress
  -> RedesignRequired
  -> Closed(cancelled|failed)

ReviewReady
  -> Closed(accepted|accepted_with_limitations|accepted_pending_human|rejected|failed)
  -> Repairing
  -> RedesignRequired
  -> WaitingOnChildren

Repairing
  -> InProgress
  -> ReviewReady
  -> Blocked
  -> RedesignRequired
  -> Closed(failed|cancelled)

RedesignRequired
  -> Proposed
  -> Authorized
  -> WaitingOnChildren
  -> Closed(cancelled|superseded)

WaitingOnChildren
  -> ReviewReady
  -> Blocked
  -> RedesignRequired
  -> Closed(decomposed|failed|cancelled)

Closed
  -> Archived

Archived
  -> no transitions
```

All transitions must be recorded.

Illegal transitions must be rejected by MetaLoop.

## Authority Model

### Authority Hierarchy

When instructions or references conflict, use this authority order:

```text
1. System and policy constraints
2. Explicit current user instruction
3. Authorized Mission Charter
4. Acceptance Contract
5. DomainProfile obligations
6. User-provided source material
7. Project-local source of truth
8. Official external documentation
9. Recent verified external sources
10. Historical AttemptRecords
11. Executor inference
12. Model prior knowledge
```

Rules:

- Lower authority cannot override higher authority.
- Inference cannot override evidence.
- Historical attempts are advisory unless revalidated.
- Model prior knowledge is never authoritative when current evidence exists.
- Time-sensitive domains require freshness metadata for external sources.
- User instruction can override project convention, but not system/policy constraints.

### Field Authority

Field ownership must be explicit.

```text
Mission intent:
  authority: user / requesting principal
  lock: locked after authorization

Scope and non-goals:
  authority: user / MetaLoop
  lock: locked after authorization

Tool and side-effect permissions:
  authority: user / policy / MetaLoop
  lock: locked after authorization

Acceptance criteria:
  authority: user / MetaLoop verifier / DomainProfile
  lock: locked after authorization

DomainProfile binding:
  authority: MetaLoop
  lock: pinned per authorized Capsule version

References:
  authority: user / SKS / executor discovery
  lock: append-only; supersede rather than overwrite

Evidence:
  authority: tools / executor / verifier / user
  lock: append-only; invalidate rather than delete

Attempt history:
  authority: MetaLoop / executor reports
  lock: append-only

Lifecycle state:
  authority: MetaLoop
  lock: legal transitions only

Derived context:
  authority: SCP
  lock: disposable; never canonical
```

### Lock Rules

After authorization:

- intent cannot be silently broadened
- acceptance cannot be weakened
- permissions cannot expand implicitly
- DomainProfile cannot change without revision
- repair cannot change the normative contract
- redesign requires explicit revision

If a locked field must change, create a Capsule revision or move to `RedesignRequired`.

## Acceptance Semantics

MetaLoop must distinguish executor claim, verification, and acceptance.

```text
Executor Claim
  -> Codex or another executor claims completion.
  -> moves to ReviewReady.

Verification
  -> MetaLoop checks evidence against the Acceptance Contract.
  -> may use hard validators, soft review, domain rules, and human review.

Acceptance
  -> authorized acceptance authority closes the contract.
  -> must cite admissible current evidence.
```

Definitions:

```text
Done:
  executor believes the work satisfies the contract.

Verified:
  checks support the completion claim.

Accepted:
  governing authority closes the Capsule with a closure outcome.
```

The executor never grants final acceptance.

Absence of errors is not evidence of completion.

Acceptance requires positive evidence matched to criteria.

### Completion Classes

Recommended completion classes:

```text
completed_verified:
  all required hard criteria have current admissible evidence.

completed_with_soft_acceptance:
  hard criteria are satisfied, but at least one required criterion depends on LLM/domain review.

completed_with_limitations:
  work is useful and evidence is present, but accepted limitations remain.

completed_pending_human_acceptance:
  internal work is complete, but final subjective/user acceptance remains.

blocked:
  required authority, dependency, clarification, reference, or environment is unavailable.

failed:
  mission cannot be satisfied under current contract and authority.
```

Missing evidence is not the same as known limitations.

If evidence is missing, the state should be `blocked`, `failed`, or `unverified`, not silently `completed_with_limitations`.

### Waivers

Waivers are allowed only if the Authority Contract permits them.

A waiver must record:

- waived criterion
- waiver authority
- reason
- evidence reviewed
- risk accepted
- effect on closure outcome

Waived criteria should not silently produce `completed_verified`.

Possible outcomes:

- `accepted_with_limitations`
- `accepted_pending_human`
- `superseded` by revised Capsule

## Evidence Model

Evidence is any recorded item used to justify a Capsule transition, route, verification, acceptance, rejection, repair, redesign, decomposition, or closure.

### Evidence Record

Each evidence item should record:

```text
evidence_id
evidence_class
producer
produced_at
source_ref
capsule_id
capsule_version
attempt_id
claim_supported
claim_contradicted
reliability
freshness
permissions
reproducibility_note
invalidation_status
```

### Evidence Classes

```text
user_evidence:
  instructions, clarifications, approvals, rejections

reference_evidence:
  docs, tickets, repository files, official docs, external sources

execution_evidence:
  commands, logs, diffs, generated artifacts, tool outputs

verification_evidence:
  tests, validators, screenshots, static analysis, type checks, benchmark results

reasoning_evidence:
  tradeoff analysis, design rationale, assumptions, rejected alternatives

negative_evidence:
  failed tests, contradictions, missing dependencies, blocked permissions, stale refs

provenance_evidence:
  source lineage, quotation/derivation/inference status
```

### Evidence Admissibility

Each acceptance criterion should declare admissible evidence classes.

Examples:

```text
command validator criterion:
  admissible: verification_evidence.command_result

research citation criterion:
  admissible: reference_evidence + provenance_evidence + reasoning_evidence

UI product fit criterion:
  admissible: human/user evidence, screenshot evidence, soft review
```

Reasoning evidence alone cannot close a hard criterion unless the Acceptance Contract explicitly permits it.

Stale evidence cannot justify closure without revalidation.

## DomainProfile Contract

A DomainProfile is a behavior-changing contract for a class of missions.

It must define:

```text
domain_id
profile_version
risk_level
default_artifact_types
required_acceptance_shape
required_evidence_classes
source_policy
freshness_policy
permission_constraints
failure_handling_rules
repair_rules
redesign_rules
decomposition_rules
audit_requirements
context_strategy
```

Initial profile families:

```text
engineering_development
algorithm_research
codex_skill_creation
deep_research
```

### Engineering Development

Typical obligations:

- changed files
- build/test/lint evidence when available
- source diff evidence
- local-only safety for private repos
- acceptance tied to command/file/schema validators where possible

### Algorithm Research

Typical obligations:

- research question
- baseline assumptions
- dataset or benchmark notes
- experiment log
- reproducibility note
- negative results
- uncertainty labeling

### Codex Skill Creation

Typical obligations:

- skill purpose
- reference corpus
- structured reference database or docs
- skill prompt contract
- installation target
- validation scenarios
- usage guide

### Deep Research

Typical obligations:

- research questions
- source policy
- recency policy
- citation/provenance evidence
- conflicting-source handling
- confidence and uncertainty
- synthesis structure

DomainProfile obligations must be satisfied or explicitly waived by authorized authority.

## Attempt History

Git history and AttemptRecords are the preferred historical memory substrate.

Chat history is not operational memory.

The current state comes from the Capsule. Historical learning comes from:

- Git commits
- diffs
- AttemptRecords
- DecisionRecords
- EvidenceRecords

### Git As Attempt Memory

LLM agents do not need to roll back the workspace to inspect history.

They can read history with:

```bash
git log
git show <commit>
git diff <commitA>..<commitB>
git show <commit>:path/to/file
```

Git history is referenceable evidence, not a prompt dump.

### AttemptRecord

An AttemptRecord represents one coherent execution attempt under one Capsule version and context snapshot.

It should record:

```text
attempt_id
capsule_id
capsule_version
executor
started_at
ended_at
context_snapshot_id
active_permissions
refs_used
actions_taken
artifacts_produced
evidence_produced
outcome
failure_reason
assumptions
repairability
staleness_markers
lesson
next_recommendation
git_commit
git_diff_ref
```

Attempt outcomes:

```text
succeeded
failed
partially_succeeded
blocked
abandoned
superseded
invalidated
stale
```

### Staleness

An attempt becomes stale when:

- user intent changes
- acceptance changes
- DomainProfile changes
- permissions change
- references change
- source code changes
- dependency versions change
- environment changes
- freshness window expires
- verifier invalidates prior evidence

Stale attempts remain useful for planning, but cannot justify current acceptance without revalidation.

## Repair, Redesign, And Decomposition

### Repair

Repair is allowed when:

- mission intent is unchanged
- acceptance criteria are unchanged
- authority is unchanged
- failure is local and bounded
- current approach remains valid
- evidence identifies the defect
- no major new risk is introduced

Examples:

- fix failing test
- restore missing file
- correct report schema
- add missing citation
- fix localized integration issue

Repair cannot modify the normative contract.

### Redesign

Redesign is required when:

- the chosen approach cannot plausibly satisfy acceptance
- core assumptions are false
- evidence contradicts the plan
- repeated repairs fail
- required authority changes
- acceptance needs reinterpretation
- DomainProfile or risk level changes
- architecture or research strategy materially changes

Redesign requires a Capsule revision or renewed authorization.

Redesign must not proceed as ordinary repair.

### Decomposition

Decomposition is required or recommended when:

- subgoals have distinct acceptance criteria
- subgoals need different authority
- subgoals can proceed independently
- risks differ by part
- different DomainProfiles are needed
- the mission is too broad to verify coherently
- child outputs must be composed into parent acceptance

Child Capsules inherit only explicitly delegated authority.

Child success does not imply parent success.

Parent Capsule should enter `WaitingOnChildren`, then review composition evidence before closure.

Decomposition is not recursion by default. It is a controlled proposal and delegation mechanism.

## Context And Memory

MetaLoop context is compiled, not remembered.

```text
Capsule + refs + role + current objective
  -> ContextCompiler
  -> ContextPacket
  -> LLM
  -> structured result
  -> Capsule update after validation
```

Rules:

- Full chat history is not operational memory.
- Full logs are not passed inline by default.
- Full repositories are not dumped into context.
- Indexed or durable content is passed as refs by default.
- Context packets are derived and disposable.
- Context packets cannot grant authority.
- Context packets cannot weaken acceptance.
- Context packets cannot omit binding constraints.

Guided autonomy remains important. Codex should receive enough intent, boundaries, refs, tools, and acceptance criteria to investigate actively inside its authority.

## Relation To Supporting Layers

### ITC

ITC is compiled from the Capsule for a specific role, phase, or invocation.

It transmits:

- intent
- authority
- responsibility
- situation
- acceptance
- output contract
- feedback rules

ITC is not the contract of record. The Capsule is.

### SCP

SCP compiles role-specific context from:

- Capsule
- ITC
- SKS refs
- current objective
- role
- lifecycle state

SCP output is disposable and non-authoritative.

### SKS

SKS backs references, provenance, permissions, freshness, and source trust.

The Capsule can refer to SKS records instead of embedding raw content.

SKS is optional in v1 implementation, but the Capsule model must be compatible with it.

### AMP

AMP carries structured events and reports:

- lifecycle transition
- evidence submitted
- attempt completed
- review requested
- approval granted
- repair requested
- redesign required
- child capsule proposed
- closure recorded

AMP is message transport. The Capsule records accepted state.

### Codex

Codex acts inside Capsule authority.

Codex can:

- inspect workspace
- edit allowed files
- run allowed commands
- produce artifacts
- write ExecutionReport
- produce AttemptRecord
- claim completion

Codex cannot:

- grant final acceptance
- expand authority
- weaken acceptance
- silently change mission intent
- turn stale evidence into current evidence

### MetaLoop

MetaLoop governs:

- Co-Design
- authorization
- contract compilation
- lifecycle transitions
- authority enforcement
- evidence validation
- review routing
- repair/redesign/decomposition decisions
- closure
- audit

## Core Invariants

These invariants are non-negotiable.

1. Every Capsule has durable identity.
2. Authorized intent is immutable except through explicit revision.
3. Acceptance criteria cannot be weakened by the executor.
4. Permissions cannot expand without recorded authority.
5. Lifecycle transitions must be legal and recorded.
6. Evidence is append-only.
7. Attempt history is append-only.
8. Completion requires current admissible evidence.
9. Acceptance requires authorized acceptance.
10. Derived context is never more authoritative than its sources.
11. Stale evidence cannot justify closure without revalidation.
12. Repair cannot change the normative contract.
13. Redesign requires explicit Capsule revision or renewed authorization.
14. Decomposition cannot create authority the parent did not have.
15. Child Capsule success does not automatically imply parent success.
16. External side effects require explicit authority.
17. DomainProfile obligations must be satisfied or explicitly waived.
18. Waivers must be recorded and cannot silently produce verified completion.
19. Contradictions must be surfaced, not silently resolved.
20. Terminal audit records must explain why closure happened.
21. A Capsule must remain reviewable by a future reader.

## v1 Canonical Scope

For v1, implement the lean constitution, not the full legal code.

Mandatory v1:

```text
MissionCapsule
DomainProfile
AcceptanceContract / VerificationPlan
EvidencePlan
EvidenceLedger
AttemptRecord
LifecycleState
ClosureOutcome
enhanced GoalContract compilation
```

Defer to v2:

```text
full SKS index
permissioned ref resolution
complete AMP event taxonomy
complex waiver semantics
evidence reliability scoring
full freshness model
multi-domain decomposition orchestration
generic external side-effect governance
```

## Relationship To Current v3 Implementation

Current v3 implements a thin slice:

```text
MissionSpec
  -> GoalContract
  -> CodexExecGoalRuntimeAdapter
  -> ExecutionReport
  -> VerificationResult
  -> SoftReviewDecision
  -> optional repair
```

This is compatible with the Capsule model:

```text
MissionSpec
  = early Mission Charter + Acceptance Contract

GoalContract
  = Codex-facing ITC subset

ExecutionReport
  = execution evidence and completion claim

VerificationResult
  = verification and closure classification

SoftReviewDecision
  = route decision

.metaloop/*
  = early structured Capsule filesystem
```

Future development should evolve the existing implementation toward Mission Capsule v1 without replacing the working v3 path.

## Development Rule

When adding a new MetaLoop feature, check it against this document.

Ask:

```text
Does it preserve Capsule authority?
Does it keep Codex execution separate from MetaLoop acceptance?
Does it avoid treating chat history as operational memory?
Does it add evidence rather than overwrite evidence?
Does it keep derived context non-authoritative?
Does it distinguish repair from redesign?
Does it respect DomainProfile obligations?
Does it remain local-first and inspectable?
```

If the answer is no, the feature needs redesign.

