---
name: metaloop
description: "Use when a local project task needs MetaLoop's lightweight protocol: deep task design before execution, Mission Capsule boundaries, structured acceptance, independent verification, repair/redesign/resume decisions, or a skill-first but not prompt-only workflow around Codex. Trigger for requests to use MetaLoop, design a mission, create or revise a Mission Capsule, run/verify/resume a MetaLoop task, or decide whether unsatisfactory output needs repair or redesign."
---

# MetaLoop

MetaLoop is a lightweight protocol layer for stabilizing Codex work on complex local tasks.

This skill is deployable as a self-contained Codex Skill. It includes a lightweight kernel script under `scripts/metaloop_kernel.py`; do not assume a separate `metaloop` package is installed in the user's environment.

Use this skill as the entry and alignment layer. Use the bundled kernel for state and checks. Do not treat natural-language skill instructions as the enforcement layer.

## Core Rule

```text
Skill handles entry and alignment.
MetaLoop CLI/schema/validators handle checks and state.
Hooks, sandbox, or wrapper runtime handle stronger non-bypassable constraints when needed.
```

MetaLoop is skill-first, not prompt-only.

## Current Product Shape

Prefer this skill-first shape for complex projects:

```text
Codex Skill entry
  -> minimal bundled kernel for state / lock / verify / audit
  -> one or more persistent Codex agent threads for intelligence and responsibility
  -> Adaptive Goal Loop for iterative problem solving
  -> shared truth through .metaloop artifacts, not through chat memory alone
```

For complex or open-ended work, use MetaLoop as a generic Adaptive Goal Loop, not a research-only workflow:

```text
Goal -> Plan -> Act -> Observe -> Evaluate -> Diagnose -> Decide -> Next Plan
```

Every domain uses the same loop. Domain extensions define evidence language, metrics, risks, and validators; they do not replace the loop with a separate task-specific process.

Do not rebuild an external orchestration loop that repeatedly starts one-shot `codex exec` workers for complex work. One-shot execution is acceptable for smoke tests, CI wrappers, or simple command-based runs, but the default mental model is persistent Codex thread agents using this kernel as their protocol backend.

For complex projects, multiple persistent threads may be useful when the responsibilities are truly different:

- `interface`: talks with the user and keeps the product/project conversation coherent.
- `design`: explores requirements deeply and drafts Mission Capsule plus VerificationSpec.
- `worker`: executes against the locked capsule without weakening verification.
- `reviewer`: reviews evidence and contract fit independently from worker self-report.
- `verifier`: runs locked validators and classifies completion, repair, redesign, or limitation status.

Register persistent agent threads in `.metaloop/threads.json` through the bundled kernel when thread ids are available:

```bash
python3 "$KERNEL" --workspace . threads register \
  --role design \
  --role-type design \
  --thread-id "<codex-thread-id>" \
  --responsibility "Draft Mission Capsule and VerificationSpec before execution."
```

Thread context is useful but not authoritative. The Mission Capsule, VerificationSpec, ExecutionReport, VerificationResult, decisions, attempts, and thread registry under `.metaloop/` are the operational truth.

For long-running goal-seeking tasks, each attempt should preserve what was learned, not just whether a command ran. Record or maintain an adaptive loop state when useful:

- goal and current plan
- observation from the latest attempt
- evaluation against the locked criteria
- diagnosis of why it did or did not work
- decision: `complete`, `continue`, `repair`, `redesign`, `pivot`, `stop`, or `escalate`
- next plan and evidence

For long-running work, record important observations and decisions as lightweight events instead of relying on private thread memory:

```bash
python3 "$KERNEL" --workspace . event append \
  --type observation \
  --agent worker \
  --summary "CUDA unavailable; full training cannot start." \
  --evidence "nvidia-smi failed" \
  --next-action "mark blocked or redesign resource gate"
```

Events are not a scheduler. They are a compact audit trail that helps agents resume, hand off, and explain why a long task changed direction.

## When To Use

Use MetaLoop when the task benefits from at least one of:

- deep design before implementation
- iterative goal seeking where success is uncertain or requires repeated attempts
- explicit scope, non-goals, constraints, or philosophical tradeoffs
- structured acceptance criteria or evidence requirements
- independent verification instead of trusting Codex self-report
- repair/redesign/resume decisions after failure or dissatisfaction
- durable `.metaloop/` artifacts for handoff or recovery

Do not use MetaLoop as a heavy multi-agent runtime by default. Prefer one Codex agent plus a structured Mission Capsule unless the task proves it needs more.

## Workflow

Set the skill kernel path before running commands:

```bash
KERNEL="<skill_dir>/scripts/metaloop_kernel.py"
```

Use `python3 "$KERNEL" ...` from the target project workspace. If the runtime exposes the skill directory path differently, resolve `scripts/metaloop_kernel.py` relative to this `SKILL.md`.

1. Inspect current MetaLoop state before proposing action:

```bash
python3 "$KERNEL" --workspace . status
python3 "$KERNEL" --workspace . threads status
python3 "$KERNEL" --workspace . event list --limit 5
```

2. Before execution, design the verification protocol. Classify the task domain, decide whether the bundled generic extension is enough, and if not, propose a task-specific ExtensionSpec plus VerificationSpec. Mark every validator with `mode` (`executable`, `manual`, or `unsupported`) and `severity` (`blocking` or `advisory`). Do not execute until the Mission Capsule, ExtensionSpec, and VerificationSpec are locked.

A capsule cannot be locked from intent alone; include rationale, non-goals, acceptance, and either executable validators or explicit `--allow-manual-only`:

```bash
python3 "$KERNEL" --workspace . design \
  --intent "<clarified intent>" \
  --rationale "<key design rationale>" \
  --constraint "<constraint>" \
  --non-goal "<non-goal>" \
  --acceptance "<acceptance criterion>" \
  --file-exists "<expected/file/path>"
```

For metric-driven work, lock a structured VerificationSpec during design instead of leaving rules in chat:

```bash
python3 "$KERNEL" --workspace . design \
  --intent "<clarified intent>" \
  --rationale "<why this gate defines completion>" \
  --non-goal "<what must not be claimed>" \
  --json-metric-gate '{"path":"summary.json","metric":"held_out.peak1_delta","operator":">=","threshold":0}'
```

Do not use `file_exists` alone for metric, research, promotion, benchmark, or quality-breakthrough tasks. A file may prove that a run produced an artifact; it does not prove that the goal was achieved. Add metric gates, baseline comparisons, resource gates, forbidden claims, attempt requirements, or manual blocking review as appropriate.

The portable kernel supports the bundled `generic` extension with `file_exists`, `command`, `forbidden_path`, `json_metric_gate`, `json_field_exists`, `file_contains`, `artifact_hash`, `forbidden_claim`, `manual_acceptance`, and `resource_gate`. Full `--extension-spec <path>` and `--verification-spec <path>` JSON objects can also be locked into the capsule.

Before designing a custom spec, inspect available extension examples under `extensions/`. The bundled generic example is `extensions/generic/examples/basic.json`.

3. If a mission exists and is ready, execute through the bundled run wrapper when a command-based execution path is available. This writes `.metaloop/execution_report.json` so verification is judging an actual run, not a chat claim:

```bash
python3 "$KERNEL" --workspace . run \
  --command "<command that performs the work>" \
  --evidence "<evidence note>"
```

When Codex itself performs the implementation, keep work aligned to `.metaloop/mission_capsule.json`, then produce an ExecutionReport through the full MetaLoop CLI when available or a command-based wrapper step when possible.

4. Judge completion through verification, not worker self-report:

```bash
python3 "$KERNEL" --workspace . verify
```

5. If interrupted or failed but the task direction is still valid, mark or resume deliberately:

```bash
python3 "$KERNEL" --workspace . mark --status running --reason "Continuing implementation around locked capsule."
```

6. If the user is dissatisfied, classify before acting:

```bash
python3 "$KERNEL" --workspace . mark --status repair_required --reason "Implementation defect; contract still valid."
python3 "$KERNEL" --workspace . mark --status redesign_required --reason "Contract boundary or acceptance must change."
```

Use the full `metaloop` CLI only when it is available and the user wants the repository implementation. The bundled kernel is the skill's portable minimum.

For repeated attempts, do not merely rerun commands. Apply the Adaptive Goal Loop before the next attempt: summarize the observation, evaluate it against locked criteria, diagnose the likely cause, choose `continue` / `repair` / `redesign` / `pivot` / `stop` / `escalate`, and make the next plan explicitly depend on the evidence from the previous attempt.

## Dissatisfaction Classification

- `repair`: target and acceptance are still correct; implementation is defective.
- `redesign`: scope, acceptance, authority, or task definition needs to change.
- `resume`: task is incomplete but direction remains correct.
- `complete`: verification passed and human acceptance is satisfied or pending.

Do not silently change a locked MissionSpec, Mission Capsule, or GoalContract. Route contract changes through redesign/revision.

## Hard Boundaries

- Mission Capsule is task truth; chat history is not operational state.
- Persistent thread context is not operational state unless summarized into `.metaloop/` artifacts.
- Multi-thread agents must coordinate through `.metaloop/` artifacts, not private memory.
- Repeated attempts must update shared understanding through observation, evaluation, diagnosis, decision, and next plan.
- Important long-task observations, decisions, blockers, and handoffs should be recorded in `.metaloop/event_log.jsonl`.
- Codex execution reports are candidate evidence, not final truth.
- Intent alone is not enough to lock a Mission Capsule.
- ExtensionSpec and VerificationSpec are locked with the Mission Capsule and carry hashes.
- Verification requires a valid ExecutionReport.
- Manual or unsupported blocking validators cannot become hard verified completion.
- Replacing a locked capsule requires a revision reason and archives the previous capsule.
- VerificationResult and user acceptance determine completion.
- Hard validators failing means not complete.
- If a core metric gate fails, say the target failed. Do not present `completed_with_limitations` or artifact production as goal success.
- Skill instructions do not provide non-bypassable guarantees.
- Do not build a parallel state system outside `.metaloop/` artifacts.

## References

- For the lightweight product direction and skill boundary, read `references/lightweight_protocol.md`.
- For current repository implementation details, inspect `README.md`, `STATE.md`, `HANDOFF.md`, and `docs/metaloop_lightweight_protocol_reframing.md` when present.
