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

ExtensionSpec describes the task/domain verification language. VerificationSpec describes this exact task's completion gates. Both are locked inside the Mission Capsule.

The bundled kernel supports the `generic` extension first:

- `file_exists`
- `command`
- `forbidden_path`
- `json_metric_gate`
- `json_field_exists`
- `file_contains`
- `artifact_hash`
- `forbidden_claim`
- `manual_acceptance`
- `resource_gate`

Agents may design an ExtensionSpec and VerificationSpec during the design phase, but workers must not weaken them after execution. The kernel records hashes over the locked extension/spec and rejects tampered specs during verification.

Each validator must classify its verification mode and severity:

- `mode=executable`: kernel can run the check.
- `mode=manual`: user/reviewer judgment is required.
- `mode=unsupported`: the task needs the check, but this kernel has no executor yet.
- `severity=blocking`: unresolved means not complete.
- `severity=advisory`: record as warning, not hard proof.

Domain-specific extensions should grow beside this generic core instead of being hardcoded into MetaLoop Core. For a new domain, the agent should first design a task-specific ExtensionSpec, risk checks, review questions, and VerificationSpec. Manual or unsupported blocking checks must not be reported as `completed_verified`.

The extension package shape is:

```text
extensions/<domain>/
  profile.json
  verification_schema.json
  examples/
```

The current skill includes `extensions/generic/` as the reference package.
