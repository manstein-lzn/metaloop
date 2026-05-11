# MetaLoop Engineering Cybernetics Principles

Date: 2026-05-09

## Position

MetaLoop should be developed as a small closed-loop control system for Codex-driven work, not as a large agent runtime.

The useful abstraction from engineering cybernetics is:

```text
Goal input
  -> controller
  -> action
  -> project/system under work
  -> output
  -> observation
  -> evaluation
  -> diagnosis/state estimate
  -> control decision
  -> next action
```

Mapped to MetaLoop:

```text
Goal input      -> Mission Capsule / GoalSpec
Controller      -> Codex agent + MetaLoop protocol
Action          -> code change / experiment / command / analysis
System          -> local project, model, benchmark, product, or workflow
Output          -> artifacts, metrics, logs, behavior
Observation     -> ObservationReport
Evaluation      -> VerificationResult
Diagnosis       -> DiagnosisReport / AdaptiveLoopState
Decision        -> complete / continue / repair / redesign / pivot / stop / escalate
Next action     -> next_plan
```

## What To Preserve

MetaLoop's successful pieces remain the foundation:

- Mission Capsule for goal, scope, constraints, non-goals, and authority.
- ExtensionSpec / VerificationSpec for locked evidence language and gates.
- ExecutionReport for what actually ran or changed.
- VerificationResult for independent gate evaluation.
- Adaptive Goal Loop for iterative learning and next-plan continuity.
- EventLog and ThreadRegistry for durable handoff and long-task state.
- Self-contained `$metaloop` skill kernel for portable protocol state.
- `metaloop_core` as the reusable state and verification backend.

Do not replace these with a new runtime layer.

## Minimal New Pieces

The control loop needs two small primitives between verification and the next attempt:

```text
ObservationReport
  -> what feedback is visible from ExecutionReport and VerificationResult

DiagnosisReport
  -> why the feedback matters, what decision follows, and what next_plan should do
```

These are generic evidence-processing artifacts. They are not domain intelligence, not a scheduler, and not a substitute for the agent's reasoning.

## Development Rules

1. Keep closed-loop structure explicit.
   Do not let complex work become `run -> run -> run`. Failed or partial verification must pass through observation, diagnosis, decision, and next plan.

2. Keep state observable.
   Important state belongs under `.metaloop/`, not only in chat memory.

3. Keep core domain-neutral.
   `metaloop_core` must not know task-specific metrics, screenshots, logs, or paper tables. Domain extensions define those evidence languages.

4. Keep constraints stable.
   Execution failure must not weaken Mission Capsule or VerificationSpec. Contract changes route through redesign.

5. Keep decisions typed.
   Use `complete`, `continue`, `repair`, `redesign`, `pivot`, `stop`, or `escalate`; do not invent vague status prose as control flow.

6. Keep the skill portable.
   Skill-only users must still get protocol state and checks without installing the full package.

7. Keep the runtime small.
   Do not add background scheduling, automatic agent pools, or CLI/TUI surfaces unless real usage proves they are required.

## First Implementation

This upgrade adds:

- `src/metaloop_core/feedback.py`
- `ObservationReport`
- `DiagnosisReport`
- `observe_workspace()`
- `diagnose_next()`
- `.metaloop/observation_report.json`
- `.metaloop/diagnosis_report.json`

The flow is:

```text
ExecutionReport + VerificationResult
  -> observe_workspace()
  -> ObservationReport
  -> diagnose_next()
  -> DiagnosisReport
  -> AdaptiveLoopState iteration
```

## Non-Goals

- No automatic research platform.
- No domain-specific validators in core.
- No new multi-agent scheduler.
- No replacement of Mission Capsule or VerificationSpec.
- No attempt to make the skill prompt a non-bypassable enforcement layer.

## Acceptance

This direction is healthy when it reduces ambiguity and prevents drift without making the codebase heavier:

- failed verification produces observable feedback
- diagnosis is recorded before the next attempt
- next plans are evidence-grounded
- core remains clean and domain-neutral
- skill remains self-contained
- full tests and import-boundary checks pass
