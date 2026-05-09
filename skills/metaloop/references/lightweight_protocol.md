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
- persistent Codex thread agents when a project needs separate long-lived responsibilities

MetaLoop should avoid leading with:

- thick runtime frameworks
- large fixed multi-agent systems
- prompt-only discipline
- repeated one-shot `codex exec` calls as the default intelligence layer for complex projects
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

## Persistent Agent Threads

For complex projects, MetaLoop should not make a Python CLI pretend to be a better Codex runtime. Codex agents should keep the natural conversation and project understanding. MetaLoop should provide protocol state.

The recommended shape is:

```text
interface thread: user conversation and project stewardship
design thread: requirement exploration and VerificationSpec design
worker thread: implementation against locked capsule
reviewer thread: independent contract/evidence review
verifier/kernel: deterministic checks from locked VerificationSpec
```

The bundled kernel records this in `.metaloop/threads.json`. The registry is not a scheduler. It is an audit and handoff artifact that records each role's `thread_id`, responsibility, status, current capsule, and last handoff artifact.

Thread context is useful for intelligence and cost control, but it is not operational truth. Multi-thread agents must synchronize through `.metaloop/` artifacts: Mission Capsule, VerificationSpec, ExecutionReport, VerificationResult, event log, attempts, decisions, and thread registry.

First version rule: define and record roles before building automatic dispatch. Do not replace one-shot `codex exec` sprawl with a heavier scheduler until real usage demands it.

## Event Log

Long-running tasks need a compact audit trail between design and final verification. The bundled kernel writes this to:

```text
.metaloop/event_log.jsonl
```

Use events for observations, decisions, actions, blockers, handoffs, verification notes, repairs, redesign notes, and general notes. Events are especially useful when an agent discovers that the current plan cannot proceed, changes experimental direction, or hands work to another thread.

Example:

```bash
python3 "$KERNEL" --workspace . event append \
  --type blocker \
  --agent worker \
  --summary "CUDA unavailable; full training cannot start." \
  --evidence "nvidia-smi failed" \
  --next-action "mark blocked or redesign resource gate"
```

Events are not operational authority. They do not unlock a capsule, modify a VerificationSpec, or mark completion. They make long-task state inspectable and resumable without forcing a complex scheduler.

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

For metric-driven or research tasks, `file_exists` can prove that an artifact exists, but it cannot prove success. Lock JSON metric gates, baseline comparisons, resource gates, forbidden claims, attempt-count evidence, or blocking manual review before execution. If the core metric fails, the run may be useful evidence, but it is not goal success.
