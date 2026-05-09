# MetaLoop Final Clean Library Plan

Date: 2026-05-09

## Current Baseline

Phase 1 created a coherent `metaloop_core` boundary, but MetaLoop is not yet a final clean library.

Current state:

- `metaloop_core` exists and does not import legacy runtime modules.
- `tools/check_core_import_boundary.py` enforces that boundary.
- The self-contained skill kernel still owns a large copy of state, schema, and verification logic.
- The legacy full repo CLI still owns significant status, verification, resume, and runtime routing logic.
- The clean library API is useful but still thin.

The remaining work is to make `metaloop_core` the real protocol backend for state and verification while keeping the `$metaloop` skill self-contained and the full CLI contained as legacy/devtool.

## Final Target Shape

```text
metaloop_core
  -> canonical protocol library
     ids, schemas, workspace state, capsule I/O, ExecutionReport I/O,
     VerificationSpec, validators, VerificationResult, thread registry,
     event log, repair/redesign vocabulary

skills/metaloop/scripts/metaloop_kernel.py
  -> self-contained portable wrapper
     either generated from core-compatible logic or kept semantically locked
     against core parity tests

src/metaloop/
  -> legacy/full repo implementation
     CLI, TUI, Codex adapters, Co-Design, prompt pack, old runtime wrappers
     may import metaloop_core, but metaloop_core may not import it
```

## Non-Negotiable Boundaries

- `metaloop_core` must not import `metaloop.cli`, `metaloop.ui`, `metaloop.tui_shell`, `metaloop.codex_adapter`, `metaloop.goal_runtime`, `metaloop.user_agent`, `metaloop.agents`, `metaloop.workers`, prompt pack, or full runtime modules.
- The skill must remain self-contained after copying `skills/metaloop/` into a Codex skill directory.
- The full CLI must keep existing user-visible behavior unless a compatibility break is explicitly documented and tested.
- Do not move Co-Design or Codex runtime intelligence into core.
- Do not build a heavy scheduler or automatic multi-agent runtime.
- Do not commit `.metaloop/`, `.venv/`, `__pycache__/`, `*.egg-info/`, or generated runtime noise.

## Execution Plan

### Phase 2: Core State And Verification Backend

Move real protocol behavior behind `metaloop_core`:

- `metaloop_core.workspace`
  - canonical `.metaloop/` path layout
  - status reader with explicit states
  - no UI rendering
- `metaloop_core.capsule`
  - load/write Mission Capsule JSON
  - schema constants and lightweight validation
  - status transition helper
  - revision archive helper
- `metaloop_core.execution`
  - ExecutionReport load/write/validate helpers
- `metaloop_core.specs`
  - ExtensionSpec / VerificationSpec normalize, hash, validate helpers
- `metaloop_core.validators`
  - generic executable validators: `file_exists`, `command`, `forbidden_path`, `json_metric_gate`, `json_field_exists`, `file_contains`, `artifact_hash`
  - manual/unsupported validator classification
- `metaloop_core.verification`
  - `verify_workspace()` or equivalent deterministic API
  - emits VerificationResult-compatible dict/data object

Acceptance for Phase 2:

- Core can design/load/verify a minimal workspace without importing full CLI.
- Core tests cover file, command, JSON metric, file_contains, artifact_hash, manual blocking, unsupported blocking, and tamper/hash checks where available.
- Existing skill package tests still pass.

### Phase 3: Skill Kernel Alignment

Make the self-contained skill kernel and core semantics stay aligned:

- Add representative parity tests that run the same design/run/verify scenario through:
  - `metaloop_core` API
  - `skills/metaloop/scripts/metaloop_kernel.py`
- Keep skill kernel portable. If it cannot import installed `metaloop_core`, it must still run standalone.
- If duplication remains, document it as generated/copy-compatible logic and add tests that catch drift.

Acceptance for Phase 3:

- Skill smoke tests pass without `pip install metaloop`.
- Core/skill parity tests pass for status, design, run, verify, thread registry, and event log.
- Skill docs mention the core/portable-kernel relationship honestly.

### Phase 4: Legacy CLI Containment

Reduce legacy/full repo leakage without rewriting user-facing behavior:

- Update CLI status/verify paths to call `metaloop_core` where appropriate.
- Keep Co-Design, prompt pack, Codex adapters, TUI shell, and old multi-agent runtime outside core.
- Add tests that legacy CLI can import `metaloop_core`, but `metaloop_core` cannot import legacy CLI/runtime modules.
- Keep current full test suite passing.

Acceptance for Phase 4:

- Existing `metaloop` command tests still pass.
- CLI docs/help continue to state legacy/devtool/fallback status.
- No new dependency from `metaloop_core` to Rich, prompt_toolkit, Codex SDK/CLI, or runtime worker modules.

## Final VerificationSpec

This work is complete only when all executable gates pass:

- `src/metaloop_core/__init__.py` exists.
- `src/metaloop_core/execution.py` exists.
- `src/metaloop_core/specs.py` exists.
- `src/metaloop_core/verification.py` contains `verify_workspace`.
- `tests/test_metaloop_core_api.py` exists.
- `tests/test_metaloop_core_verification.py` exists.
- `tests/test_metaloop_core_skill_parity.py` exists.
- `tools/check_core_import_boundary.py` exists.
- `python3 tools/check_core_import_boundary.py` passes.
- `PYTHONPATH=src python3 -c "from metaloop_core import WorkspaceState; from metaloop_core.verification import verify_workspace; print('core ok')"` passes.
- `grep -R "from metaloop_core" -n src/metaloop tests | grep -q .` passes, proving legacy repo consumers now use core.
- `grep -R "metaloop_core" -n skills/metaloop docs README.md STATE.md | grep -q .` passes, proving docs/skill acknowledge the core boundary.
- `.venv/bin/pytest tests/test_metaloop_core_api.py tests/test_metaloop_core_verification.py tests/test_metaloop_core_skill_parity.py tests/test_skill_package.py -q` passes.
- `.venv/bin/pytest -q` passes.
- `git diff --check` passes.

Manual reviewer gate:

- Confirm `metaloop_core` is now the real protocol backend for state/verification primitives, not only a thin placeholder.
- Confirm the skill remains self-contained.
- Confirm legacy CLI is contained and not presented as the main product interface.

## Repair / Redesign Rules

- If a test or validator fails but the target architecture still makes sense, repair implementation.
- If skill self-contained deployment conflicts with core reuse, keep the skill self-contained and add parity/generation tests instead of forcing a runtime package dependency.
- If CLI containment requires broad Co-Design or Codex runtime rewrites, stop and redesign the phase boundary.
- If `metaloop_core` starts accumulating UI, TUI, prompt, or Codex transport concerns, mark redesign_required and split the boundary again.
