# MetaLoop Clean Library Mission Plan

Date: 2026-05-09

## Goal

Turn MetaLoop from an evolving single package into a cleaner library shape while preserving the current skill-first product direction.

The target shape is:

```text
metaloop_core
  -> schemas, capsule, verification, validators, workspace state,
     thread registry, event log, repair/redesign primitives

skills/metaloop
  -> Codex Skill entry, references, examples, bundled kernel wrapper

metaloop full repo CLI
  -> legacy/devtool/CI/fallback wrapper around core and historical runtime
```

## Design Rationale

MetaLoop now has two valid consumers of the same protocol: the self-contained `$metaloop` skill and the legacy full repository CLI. Keeping all core protocol logic mixed with CLI/TUI/Codex adapters makes it difficult to trust, reuse, test, or package the project. A clean library boundary should let the skill, CLI, and future multi-thread agents share the same state and validation semantics.

The first clean-library pass should be deliberately conservative. It should extract stable protocol primitives without rewriting the full runtime, TUI, prompt pack, or Codex adapters. The purpose is to create a reliable core API and import boundary, not to redesign behavior.

## Proposed Package Boundary

```text
src/metaloop_core/
  __init__.py
  ids.py
  schemas.py
  workspace.py
  capsule.py
  verification.py
  validators.py
  thread_registry.py
  event_log.py
  repair_redesign.py

src/metaloop/
  cli.py
  co_design.py
  goal_runtime.py
  codex_adapter.py
  user_agent.py
  tui_shell.py
  ... legacy/full repo implementation wrappers
```

Phase 1 can use compatibility imports from `metaloop.*` to avoid a risky big-bang move, but the direction is that core code must not import UI, TUI, Codex SDK, Codex exec, prompt pack, or legacy multi-agent runtime modules.

## Staged Execution

### Phase 0: Lock The Contract

- Lock this mission into `.metaloop/mission_capsule.json`.
- Register current interface/design thread in `.metaloop/threads.json` when a thread id is available; if not, record a local placeholder note.
- Record major decisions in `.metaloop/event_log.jsonl`.

### Phase 1: Core API Skeleton

- Create `src/metaloop_core/`.
- Add a public API surface in `metaloop_core/__init__.py`.
- Move or wrap stable primitives first: ids/time helpers, workspace paths, thread registry, event log, VerificationSpec-oriented checks.
- Keep old imports working.
- Add `tests/test_metaloop_core_api.py`.

### Phase 2: Verification And State Boundary

- Move generic verification primitives behind `metaloop_core.verification` and `metaloop_core.validators`.
- Expose a small programmatic API such as `WorkspaceState`, `load_capsule`, `write_execution_report`, and `verify_workspace`.
- Keep the skill-bundled kernel behavior semantically aligned with the core API.
- Add import-boundary tests that forbid `metaloop_core` from importing `metaloop.cli`, `ui`, `tui_shell`, `codex_adapter`, `goal_runtime`, `user_agent`, `agents`, or `workers`.

### Phase 3: Skill Kernel Wrapper Cleanup

- Decide whether the self-contained skill kernel should remain generated/copy-pasted or become a thin wrapper when full package is installed.
- Preserve self-contained deployment: copying `skills/metaloop/` into a Codex skill directory must still work without `pip install metaloop`.
- Add tests proving installed skill smoke behavior and full package core behavior agree on representative status/design/run/verify cases.

### Phase 4: Legacy CLI Containment

- Update full CLI docs and help to treat CLI/TUI as legacy/devtool.
- Keep `metaloop design/run/status/verify/resume` behavior working.
- Avoid migrating prompt-heavy Co-Design or full goal runtime until the core API is stable.

## Non-Goals

- Do not delete the legacy full repo CLI/TUI in this mission.
- Do not rewrite Co-Design, prompt pack, Codex SDK bridge, or goal runtime.
- Do not build a heavy multi-agent scheduler.
- Do not make the skill depend on a full package install.
- Do not change user-facing MetaLoop protocol semantics just to make imports prettier.
- Do not commit generated noise such as `.metaloop/`, `__pycache__/`, `.venv/`, or `*.egg-info/`.

## VerificationSpec

The first hard gate for this mission is not subjective cleanliness. It is a set of executable checks:

- `src/metaloop_core/__init__.py` exists.
- `tests/test_metaloop_core_api.py` exists.
- `README.md` mentions `metaloop_core` and the clean library boundary.
- `STATE.md` mentions the clean library boundary and the CLI legacy containment.
- `PYTHONPATH=src python3 -c "import metaloop_core; print(metaloop_core.__name__)"` succeeds.
- `python3 tools/check_core_import_boundary.py` confirms core does not import forbidden legacy runtime modules.
- `.venv/bin/pytest tests/test_metaloop_core_api.py tests/test_skill_package.py -q` passes.
- `.venv/bin/pytest -q` passes.
- `git diff --check` passes.

Manual review remains required for whether the boundary is actually understandable and worth keeping. The executable gates prevent fake completion; the manual review decides whether the design is good enough to continue.

## Repair / Redesign Rules

- If tests fail but the package boundary remains correct, repair implementation.
- If extracting core requires broad rewrites of Co-Design or goal runtime, stop and redesign the phase boundary.
- If the self-contained skill stops working without package install, treat as blocking failure.
- If the import-boundary test forces awkward code duplication, pause and redesign the core API rather than weakening the boundary silently.
