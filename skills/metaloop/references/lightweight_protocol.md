# MetaLoop Lightweight Protocol Reference

MetaLoop is Codex's task design and stable execution protocol layer.

## Product Position

MetaLoop should preserve:

- deep Design
- structured Mission Capsule
- durable `.metaloop/` artifacts
- independent VerificationResult
- repair/redesign/resume decisions
- Codex SDK UserAgent as the human-facing entry
- a bundled lightweight kernel for one-click skill deployment

MetaLoop should avoid leading with:

- thick runtime frameworks
- large fixed multi-agent systems
- prompt-only discipline
- code mechanisms that do not correspond to repeated real failures

## Skill Boundary

Skill can carry the system, but cannot alone enforce non-bypassable constraints.

Use this split:

```text
$metaloop skill
  -> entry, alignment, design discipline, action suggestions

Bundled scripts / schemas / validators
  -> deterministic checks, artifact writes, status, verification

Full MetaLoop CLI, when installed
  -> richer design/run/verify/resume implementation

hooks / sandbox / wrapper runtime
  -> stronger constraints when needed
```

## Minimal Capsule Truth

A Mission Capsule should be readable by both user and Codex. Keep it focused on:

- intent
- context
- design rationale
- constraints
- non-goals
- acceptance criteria
- forbidden paths
- evidence requirements
- verification plan
- current status

It is not a full transcript.

## Decision Discipline

When output is unsatisfactory, classify before executing:

- `repair`: correct contract, defective implementation
- `redesign`: incorrect/incomplete contract, scope, authority, or acceptance
- `resume`: incomplete work, direction still valid
- `complete`: verification passed and human acceptance is satisfied or pending

Never let a worker repair silently mutate locked contract boundaries.

## Deployment Shape

The skill should be useful immediately after copying/installing the skill folder. It must not require the target machine to have the MetaLoop repository installed as a Python package.

The portable minimum is:

```text
SKILL.md
references/lightweight_protocol.md
scripts/metaloop_kernel.py
```

The bundled kernel owns the minimal `.metaloop/mission_capsule.json` and `.metaloop/verification_result.json` flow. The full repository CLI can supersede it when available, but the skill must not depend on that external install for its core protocol behavior.

The bundled kernel also writes `.metaloop/execution_report.json` when execution can be represented as one or more workspace commands. Verification should require this report before claiming completion, because a validator pass without a recorded execution can hide skipped or drifted work.

The minimum design gate is intentionally stricter than a plain prompt: intent alone is insufficient. A locked capsule should include design rationale, at least one explicit non-goal, acceptance criteria, and a hard verification path unless the user explicitly accepts manual-only review.

## VerificationSpec

VerificationSpec is the structured completion contract locked inside the Mission Capsule. The bundled kernel supports the `generic` extension first:

- `file_exists`
- `command`
- `forbidden_path`
- `json_metric_gate`

Agents may design a VerificationSpec during the design phase, but workers must not weaken it after execution. The kernel records an `extension_hash` over the locked spec and rejects tampered specs during verification.

Domain-specific extensions should grow beside this generic core instead of being hardcoded into MetaLoop Core. A future StateTune extension should add validators for summary metrics, promotion gates, forbidden claims/features, and resource gates.
