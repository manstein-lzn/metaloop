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
