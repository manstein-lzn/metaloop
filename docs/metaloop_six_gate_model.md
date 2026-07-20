# MetaLoop Six-Gate Model

Date: 2026-05-12

V2 implements these gates over an explicit Task and immutable subject chain.
The State Checkpoint includes open Attempt records and a freshness-checked
RecoveryView; Verification follows one exact Attempt/Evaluation hash chain;
Task lifecycle mutation uses compare-and-swap in SQLite.

MetaLoop is not an agent runtime. Codex remains the intelligence layer:
understanding, design, search, coding, experiments, interpretation, and
strategy. MetaLoop owns the critical control points that keep long work
recoverable, verifiable, and observable.

```text
Codex agent = brain and hands
MetaLoop = gates, instruments, checklist, black box, and acceptance record
```

## The Six Gates

### 1. Design Gate

Before substantial execution, Codex must clarify:

- goal
- non-goals
- constraints
- evidence
- success criteria
- stopping conditions
- repair/redesign triggers

MetaLoop code only locks this as a Task ContractRevision and VerificationSpec.
It does not design the solution. Mission Capsule is the V1 migration shape.

### 2. State Checkpoint

After important actions, Codex records compact state:

- Attempt records and exact evidence for execution progress
- DecisionEvents for observations, decisions, blockers, and handoffs
- RecoveryView for context growth, task switching, or thread reset

The point is continuity, not control.

### 3. Verification Gate

Codex may explain results, but it cannot declare completion by self-report.
Completion must come from locked validators, required evidence, or explicit
manual acceptance. Failed metric gates remain failed targets.

### 4. Adaptive Loop

If the result is partial or failed, Codex must classify and learn before trying
again:

```text
Observe -> Evaluate -> Diagnose -> Decide -> Next Plan
```

Mechanical retry is not acceptable for long or uncertain tasks. A new attempt
must be grounded in what the previous attempt changed or revealed.

### 5. Control Point

Humans and outer wrappers control work through explicit files under
`.metaloop/control/`. Workers and activation wrappers read these files at safe
points. Observers and dashboards must not silently approve resources, route
work, or mutate locked contracts.

### 6. Observation Surface

The user must be able to see current state without reading agent chat:

- goal
- current plan
- latest event
- latest verification status
- adaptive decision
- pending controls
- context checkpoint health
- outbox/inbox state
- blocked or waiting state

The first surface is `observe --json` or `observe --format brief`. A dashboard
may render the same summaries, but should remain read-only unless it writes
explicit control files.

## Safe-Point Protocol

Codex workers should check and update MetaLoop at predictable safe points.

Before starting an attempt:

- inspect status, pending controls, and relevant context checkpoints
- confirm the Task, ContractRevision, and VerificationSpec are still the active target
- record an event if an important assumption or blocker is found

Before expensive work:

- check `.metaloop/control/`
- require explicit approval if a locked resource gate says so
- avoid starting if halt or revise-contract intent is pending

After an attempt:

- attach or update exact Attempt evidence
- run verification
- record adaptive observation/evaluation/diagnosis/decision/next plan if not
  complete
- refresh RecoveryView when the task is long or handoff-prone

Before claiming completion:

- verify locked gates passed or manual acceptance is explicitly pending
- report unsupported/manual blockers honestly
- do not weaken acceptance after seeing results

Before handoff:

- write an event
- update thread registry or outbox/inbox if relevant
- update context checkpoint enough for the next agent to resume

## Product Boundary

Do:

- use prompt and examples to guide Codex intelligence
- use code for durable state, verification, audit, and observation
- keep activation one-shot and explicit
- keep context checkpoints compact and human-readable

Do not:

- build a hidden scheduler
- build a second agent brain
- turn context checkpoints into transcripts or vector memory
- let dashboards route work silently
- let workers modify locked verification to fit results
