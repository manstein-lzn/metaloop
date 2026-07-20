# Prompt-First / Code-Backed MetaLoop

MetaLoop should use Codex intelligence directly and keep the kernel small.

Core rule:

```text
Prompt handles intelligence. Code handles truth.
```

Use prompt / skill instructions / examples for:

- understanding the task
- asking sharp questions
- designing Mission Capsule and VerificationSpec
- interpreting evidence
- diagnosing failure
- choosing continue / repair / pivot / redesign / stop / escalate
- planning the next high-signal attempt

Use code / kernel / validators for:

- Project/Task identity and dependency references
- immutable ContractRevision, sealed Attempt, and Evaluation hashes
- Task compare-and-swap and one-open-Attempt uniqueness
- exact replay fingerprints and recorded retry reasons
- monotonic DecisionEvent cursors and RecoveryView freshness
- locked state
- schema and hash checks
- ExecutionReport and VerificationResult
- ObservationReport and DiagnosisReport when available
- Adaptive Goal Loop state
- event log and thread registry
- deterministic validation
- audit and resume
- locking and rechecking governing-document and module-contract refs/hashes

Prefer examples before framework code. For domain behavior, write playbooks and VerificationSpec examples first. Promote behavior into code only when it must be machine-checked, routed, recovered, or shared across agents as durable state.

Avoid code-first drift:

- Do not add a new Python module for every useful reasoning pattern.
- Do not hardcode domain strategy in MetaLoop Core.
- Do not turn the skill into prompt-only state; key facts still need `.metaloop/` artifacts.
- Do not make the kernel a scheduler or low-quality Codex replacement.

When a failed or partial verification happens, let the agent reason deeply in natural language, but record the minimum durable result:

```text
observation
evaluation_status
diagnosis
decision
next_plan
evidence
```

In v2 this durable result is a Task- or Project-scoped DecisionEvent. The event
records that the judgment occurred; Task lifecycle changes only through the
transactional service layer. Rich reasoning still does not belong in schema.

This preserves intelligence without losing auditability.

For engineering work, code validates only the explicitly declared
`repair | extension | redesign` value. It must not inspect diagnosis prose or
keywords to manufacture that semantic decision. Architecture content remains in
the project's governing documents; MetaLoop stores refs, hashes, scope, and the
migration-plan binding required for redesign.
