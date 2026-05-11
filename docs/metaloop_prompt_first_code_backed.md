# MetaLoop Prompt-First / Code-Backed Discipline

Date: 2026-05-09

## Position

MetaLoop should not turn agent intelligence into a large Python framework.

Use this split:

```text
Prompt handles intelligence.
Code handles truth.
Examples transfer skill.
Validators build trust.
Kernel stays small.
```

Modern Codex agents are strong enough to do much of the understanding, diagnosis, strategy, and reflection work through prompt protocol. MetaLoop should use that strength instead of replacing it with brittle code.

## Prompt Responsibilities

Use prompts, skill instructions, playbooks, and examples for work that requires judgment:

- understanding the user's real goal
- exploring requirements and tradeoffs
- forming hypotheses
- designing VerificationSpec and domain extensions
- diagnosing failed or partial results
- interpreting observations
- deciding whether to continue, repair, pivot, redesign, stop, or escalate
- proposing the next high-signal plan
- explaining uncertainty and residual risk to the user

These are intelligence tasks. Hardcoding them too early makes MetaLoop rigid and hard to maintain.

## Code Responsibilities

Use code only where durable truth, verification, and recovery matter:

- writing Mission Capsule
- locking ExtensionSpec / VerificationSpec
- validating schema and hashes
- writing ExecutionReport, VerificationResult, ObservationReport, DiagnosisReport, AdaptiveLoopState, event log, and thread registry
- running deterministic validators
- summarizing current workspace state
- preventing accidental artifact drift
- enabling resume and handoff

These are state and trust tasks. Leaving them only in prompt makes the system hard to audit and easy to drift.

## Examples Over Frameworks

For domain behavior, prefer examples and playbooks before code frameworks:

```text
extensions/<domain>/examples/*.json
references/<domain>_playbook.md
references/<domain>_reflection_template.md
references/<domain>_forbidden_claims.md
```

Only promote a pattern into code when repeated usage proves that it must be machine-checked, routed, or recovered.

## Schema-Light Rule

Schemas should define minimum durable fields, not the whole thought process.

Good durable fields:

- goal
- plan
- observation
- evaluation_status
- diagnosis
- decision
- next_plan
- evidence
- validator results

Keep rich reasoning in markdown notes, events, or agent messages unless code needs to inspect it.

## Avoid Code-First Drift

Do not add new Python modules just because a prompt says something important. Add code only when at least one is true:

- the value must persist across sessions
- validators need to inspect it
- status/resume needs to route on it
- reviewers need an audit trail
- multiple agents need a shared handoff artifact

Otherwise, improve the prompt protocol or add an example.

## Relationship To Current Core

Current `metaloop_core` already owns the small code-backed truth layer:

- Mission Capsule
- ExtensionSpec / VerificationSpec
- ExecutionReport
- VerificationResult
- ObservationReport
- DiagnosisReport
- Adaptive Goal Loop
- EventLog
- ThreadRegistry
- Routable work-unit schemas
- Pure router decisions
- One-shot tick and relay results

Do not keep adding report types by default. Use the existing loop unless a new state object has a clear verification or recovery role.

## Acceptance

MetaLoop is on track when:

- Codex agent remains the main intelligence
- skill prompt gives strong behavioral protocol
- kernel state is small and durable
- validators remain deterministic
- domain behavior grows through examples first
- core stays domain-neutral
- failures produce observation, diagnosis, and next-plan continuity
- the codebase gets simpler to reason about, not larger by reflex
