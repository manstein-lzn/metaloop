# MetaLoop Troubleshooting

MetaLoop is now used through the Codex `$metaloop` skill and its bundled kernel. Troubleshooting should start with the `.metaloop/` artifacts in the target workspace.

## Skill Is Not Found

Confirm the skill folder exists:

```bash
ls "${CODEX_HOME:-$HOME/.codex}/skills/metaloop/SKILL.md"
```

If it is missing, use [codex_install_metaloop_skill.md](codex_install_metaloop_skill.md) to install the self-contained skill package.

## Kernel State Looks Missing

From the target project, resolve the skill kernel path and inspect status:

```bash
KERNEL="${CODEX_HOME:-$HOME/.codex}/skills/metaloop/scripts/metaloop_kernel.py"
python3 "$KERNEL" --workspace . status
```

If no capsule exists, ask Codex to use `$metaloop` and start with design. Intent alone is not enough; the design should include rationale, non-goals, acceptance, and VerificationSpec.

## Verification Cannot Complete

Check the current artifacts:

```bash
python3 "$KERNEL" --workspace . status
python3 "$KERNEL" --workspace . verify
```

Common causes:

- `.metaloop/execution_report.json` is missing.
- A hard validator failed.
- A manual or unsupported blocking validator still requires human/reviewer acceptance.
- The locked VerificationSpec hash changed after design.

Do not weaken the VerificationSpec after execution. If the spec is wrong, mark redesign and lock a revised capsule.

## Long Task Is Drifting

Record observations and decisions instead of relying on chat memory alone:

```bash
python3 "$KERNEL" --workspace . event append \
  --type observation \
  --agent worker \
  --summary "Latest attempt produced artifacts but metric gate failed." \
  --evidence ".metaloop/verification_result.json" \
  --next-action "Diagnose failure and record adaptive next plan."
```

For repeated attempts, use the adaptive loop: observe, evaluate, diagnose, decide, then plan the next attempt.

## Handoff Does Not Move Downstream

For routable work units, `tick` and `relay` are explicit one-shot operations:

```bash
python3 "$KERNEL" --workspace . tick --envelope job_envelope.json
python3 "$KERNEL" --workspace . relay --dispatch-map dispatch_map.json
```

Common causes:

- `job_envelope.json` is missing or has a stale `envelope_hash`.
- `.metaloop/verification_result.json` is missing, failed without an adaptive decision, requires Codex reviewer judgment, or requires user authority.
- `.metaloop/outbox/<target>.json` was written, but `dispatch_map.json` lacks that target.
- the dispatch route has no explicit envelope template, so relay returns `needs_design`.
- the target workspace path is wrong.

Relay must not invent downstream mission content. Add or revise the target project's dispatch map and envelope template, then rerun relay.

## Tests

```bash
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```
