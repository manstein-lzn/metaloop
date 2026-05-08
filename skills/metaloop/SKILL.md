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

## When To Use

Use MetaLoop when the task benefits from at least one of:

- deep design before implementation
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
```

2. If there is no locked mission or the user's intent is underspecified, design first. A capsule cannot be locked from intent alone; include rationale, non-goals, acceptance, and either hard validators or explicit `--allow-manual-only`:

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

The portable kernel currently supports the bundled `generic` extension with `file_exists`, `command`, `forbidden_path`, and `json_metric_gate`. A full `--verification-spec <path>` JSON object can also be locked into the capsule.

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

## Dissatisfaction Classification

- `repair`: target and acceptance are still correct; implementation is defective.
- `redesign`: scope, acceptance, authority, or task definition needs to change.
- `resume`: task is incomplete but direction remains correct.
- `complete`: verification passed and human acceptance is satisfied or pending.

Do not silently change a locked MissionSpec, Mission Capsule, or GoalContract. Route contract changes through redesign/revision.

## Hard Boundaries

- Mission Capsule is task truth; chat history is not operational state.
- Codex execution reports are candidate evidence, not final truth.
- Intent alone is not enough to lock a Mission Capsule.
- VerificationSpec is locked with the Mission Capsule and carries an extension hash.
- Verification requires a valid ExecutionReport.
- VerificationResult and user acceptance determine completion.
- Hard validators failing means not complete.
- Skill instructions do not provide non-bypassable guarantees.
- Do not build a parallel state system outside `.metaloop/` artifacts.

## References

- For the lightweight product direction and skill boundary, read `references/lightweight_protocol.md`.
- For current repository implementation details, inspect `README.md`, `STATE.md`, `HANDOFF.md`, and `docs/metaloop_lightweight_protocol_reframing.md` when present.
