# MetaLoop Multi-Thread Agent Protocol

MetaLoop should not make an external CLI orchestration loop pretend to be the main intelligence layer. Codex agents keep long-lived reasoning context; MetaLoop records task truth and verification state.

## Shape

```text
Codex Skill entry
  -> persistent Codex thread agents
  -> .metaloop Mission Capsule / VerificationSpec / thread registry
  -> worker ExecutionReport as candidate evidence
  -> kernel VerificationResult as independent acceptance
```

The protocol is intentionally small. It records thread roles and handoff boundaries; it does not schedule background agents by itself.

## Thread Registry

The bundled skill kernel records persistent agent threads in:

```text
.metaloop/threads.json
```

Register a thread when a Codex thread id is available:

```bash
python3 "$KERNEL" --workspace . threads register \
  --role design \
  --role-type design \
  --thread-id "<codex-thread-id>" \
  --responsibility "Draft Mission Capsule and VerificationSpec before execution."
```

Inspect the registry:

```bash
python3 "$KERNEL" --workspace . threads status
```

Update handoff state:

```bash
python3 "$KERNEL" --workspace . threads update \
  --role design \
  --status handoff_required \
  --note "Design is ready for independent review."
```

## Canonical Roles

- `interface`: talks with the user and preserves project-level intent.
- `design`: explores requirements and drafts Mission Capsule plus VerificationSpec.
- `worker`: executes against the locked capsule without weakening verification.
- `reviewer`: checks contract fit and evidence independently from worker self-report.
- `verifier`: runs locked validators and classifies completion, repair, redesign, or limitation status.

Custom role names are allowed when a project needs them, but responsibilities must stay explicit.

## Operational Truth

Thread context is useful but not authoritative. Shared truth must live in `.metaloop/` artifacts:

- `mission_capsule.json`
- locked `extension_spec` and `verification_spec` inside the capsule
- `execution_report.json`
- `verification_result.json`
- `threads.json`
- `event_log.jsonl`
- attempts, decisions, and revision archives

If a thread learns something important, it should summarize that into the relevant artifact instead of relying on private chat memory.

## Event Log

Use `.metaloop/event_log.jsonl` for the small facts that make a long task resumable:

- observations
- decisions
- actions
- blockers
- handoffs
- verification notes
- repair/redesign notes

Example:

```bash
python3 "$KERNEL" --workspace . event append \
  --type observation \
  --agent worker \
  --summary "CUDA unavailable; full training cannot start." \
  --evidence "nvidia-smi failed" \
  --next-action "mark blocked or redesign resource gate"
```

Events do not change locked contracts and do not prove completion. They are the lightweight continuity layer between intelligent agent work and deterministic verification.

## Boundaries

- Do not use one-shot `codex exec` as the default intelligence layer for complex projects.
- Do not build an automatic multi-agent scheduler before real usage demands it.
- Do not let worker threads modify locked verification after seeing results.
- Do not use `file_exists` alone for metric, benchmark, promotion, or research breakthrough tasks.
- If the core metric gate fails, report target failure even when artifacts were produced.
