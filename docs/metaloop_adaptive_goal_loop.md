# MetaLoop Adaptive Goal Loop

Date: 2026-05-09

## Position

MetaLoop should converge on a generic goal-seeking loop, not a research-specific workflow.

The shared loop is:

```text
Goal
  -> Plan
  -> Act
  -> Observe
  -> Evaluate
  -> Diagnose
  -> Decide
  -> Next Plan
  -> repeat until success, stop, block, or redesign
```

Research tasks, engineering debugging, frontend polishing, benchmark optimization, paper reproduction, and data pipeline hardening all fit this shape. Research is only a high-uncertainty, high-cost instance of the same loop.

## Core Principle

MetaLoop Core owns the loop vocabulary and durable state. Domain extensions own evidence language and validators.

```text
MetaLoop Core
  -> Goal / Plan / Observation / Evaluation / Diagnosis / Decision / Next Plan
  -> Mission Capsule, VerificationSpec, ExecutionReport, VerificationResult
  -> Attempt and event memory

Domain Extension
  -> evidence types
  -> metrics and thresholds
  -> validators and extractors
  -> domain-specific risk rules

Codex Agent
  -> understanding, hypothesis, implementation, interpretation, strategy
```

Do not hardcode StateTune, MAPE, frontend, backend, or paper-reproduction rules into `metaloop_core`. Put those rules in ExtensionSpec / VerificationSpec / examples.

## Why This Matters

One-shot task framing asks whether work is done. Complex goal seeking also needs to ask what was learned.

A failed attempt should produce more than `failed`:

- what was tried
- what was observed
- whether the result satisfied the goal
- why it likely failed
- which assumption changed
- what the next plan is and why it is more informative

Without this discipline, a long-running agent can keep trying variants, forget why they failed, weaken the target, or report artifact production as success.

## Minimal State Shape

The lightweight core state is `.metaloop/adaptive_loop.json`:

```json
{
  "schema": "metaloop.adaptive_goal_loop",
  "goal": "Reach the target under locked acceptance criteria.",
  "status": "active",
  "current_plan": "Run the next high-signal attempt.",
  "success_criteria": ["VerificationSpec passes"],
  "known_facts": ["Previous attempt improved subset but failed held-out gate"],
  "open_questions": ["Is the bottleneck data quality or model capacity?"],
  "iterations": []
}
```

Each iteration records the full learning loop:

```json
{
  "schema": "metaloop.adaptive_goal_iteration",
  "plan": "Run the next high-signal attempt.",
  "observation": "The metric improved on subset but regressed on held-out.",
  "evaluation_status": "not_satisfied",
  "diagnosis": "The plan likely overfit the subset and does not promote.",
  "decision": "continue",
  "next_plan": "Add held-out slice analysis before another training run.",
  "evidence": [".metaloop/verification_result.json", "analysis/summary.json"]
}
```

## Decisions

The generic decision vocabulary is:

- `complete`: success criteria are satisfied.
- `continue`: goal remains valid; more information or another attempt is needed.
- `repair`: implementation is defective; target and plan direction remain valid.
- `redesign`: goal, acceptance, scope, or VerificationSpec is wrong or incomplete.
- `pivot`: the current strategy direction is likely wrong; keep the goal but change approach.
- `stop`: goal should not continue under current constraints.
- `escalate`: blocked by resource, permission, policy, or human authority.

This vocabulary is deliberately domain-neutral.

## Relationship To Mission Capsule

Mission Capsule remains the task constitution: goal, constraints, non-goals, acceptance, ExtensionSpec, and VerificationSpec.

Adaptive Goal Loop is the iterative learning state under that constitution. It does not unlock or weaken the capsule. If diagnosis shows the capsule is wrong, the decision should be `redesign`, followed by an explicit capsule revision.

## Relationship To VerificationSpec

VerificationSpec decides whether the current result satisfies locked gates. Adaptive Loop records what the agent learned from that result and what should happen next.

The two must not collapse into each other:

- Verification without diagnosis can prove failure but not guide the next attempt.
- Diagnosis without verification can become storytelling.

## First Implementation

The first implementation is intentionally small:

- `src/metaloop_core/adaptive_loop.py`
- `.metaloop/adaptive_loop.json` helpers
- validation for loop and iteration shape
- generic `decide_next()` vocabulary
- tests for create, append, persist, validate, and decision routing

It does not include automatic agent scheduling, experiment execution, or domain-specific analysis.

## Acceptance

The abstraction is correct when:

- it applies equally to research, engineering, frontend, benchmark, and operational tasks
- no domain rules are hardcoded in core
- every failed or partial attempt can preserve observation, evaluation, diagnosis, decision, and next plan
- domain extensions remain responsible for evidence types and validators
- Mission Capsule and VerificationSpec remain authoritative for scope and completion
