# MetaLoop Engineering Governance vNext

Status: implemented first vertical slice

Document type: normative specification

Authority: governs the engineering-governance additions to MetaLoop

Supersedes: keyword-based semantic decision inference on the active path;
narrows and extends the existing six-gate protocol

Last verified: 2026-07-11

Exit condition: satisfied for the first vertical slice; further capabilities
require a new governing revision

## Objective

Make MetaLoop a small engineering control plane that prevents design drift,
implicit scope growth, and repair work from silently becoming redesign.

MetaLoop must lock the engineering decision boundary before execution and
recheck it before execution and verification. It does not design architecture,
become an agent runtime, or duplicate project documentation.

## Non-goals

- No scheduler, watcher, daemon, agent pool, or workflow runtime.
- No MissionForge-specific behavior or product semantics.
- No keyword-based inference of repair, extension, or redesign.
- No second architecture source of truth under `.metaloop/`.
- No automatic judgment that a module boundary or API design is correct.
- No broad rewrite of Mission Capsule, verification, routing, or relay.

## First Vertical Slice

The `design` command may lock an optional `engineering_governance` envelope:

```text
change_type
governing_document ref + sha256
module_contract refs + sha256
allowed_paths
migration_plan ref + sha256 (required for redesign)
```

The envelope contains identities and hashes, not copied architecture prose.
Paths are workspace-relative files and must remain within the workspace.

### Change types

- `repair`: the governing design and public contracts remain correct; the
  implementation violates them.
- `extension`: behavior grows without changing existing ownership, authority,
  state semantics, or public contract meaning.
- `redesign`: the goal, authority, state model, module responsibility, public
  contract meaning, permission model, or time model changes.

The author or intelligent agent must choose the change type explicitly and
provide rationale through the existing Mission Capsule design rationale. Code
validates the declared value but never infers it from prose.

### Design gate

When engineering governance is requested:

1. `change_type`, `governing_document`, at least one `module_contract`, and at
   least one `allowed_path` are required.
2. Every referenced file must exist inside the workspace and is locked by its
   SHA-256 content hash.
3. `redesign` additionally requires a migration plan.
4. Non-redesign work must not attach a migration plan merely to bypass the
   classification boundary.

### Execution and verification gate

Before a command runs and before completion is verified, MetaLoop revalidates:

- referenced files still resolve inside the workspace;
- locked hashes still match;
- the envelope shape and redesign rules remain valid.

Drift fails closed with an actionable error. Changing a governing document or
module contract requires an explicit Mission Capsule revision so the previous
capsule remains archived.

## Ownership

- Project `docs/` own architecture content and module contracts.
- Mission Capsule owns the locked task and governance envelope.
- `metaloop_core.engineering_governance` owns deterministic governance
  validation and hash verification.
- The portable skill kernel mirrors only this small protocol surface and is
  covered by parity tests.
- Existing verification remains completion authority.

## Acceptance

- Existing non-engineering capsules remain valid.
- Engineering design fails without a governing document, module contract, or
  allowed path.
- Redesign fails without a migration plan.
- Repair, extension, and redesign are never inferred from prose.
- Referenced content drift blocks execution and verification.
- A valid engineering capsule can execute and reach `completed_verified`.
- Core and portable skill behavior agree for the same governed task.
- Import-boundary tests and the full existing test suite pass.

## Follow-up, Not This Slice

- Allowed-path enforcement through hooks or an outer sandbox.
- Machine-readable dependency-layer contracts and import graph validators.
- Architecture alarms for repeated patches or competing authorities.
- A redesign helper that proposes a new worktree and cutover checklist.
- MissionForge dogfood after this slice proves stable in MetaLoop itself.

## Shipped Reality

The first slice is implemented in `metaloop_core.engineering_governance` and the
portable skill kernel. Existing capsules remain valid. Governed capsules lock
document hashes and are revalidated before run and verify. Core/skill parity,
negative drift tests, explicit-decision tests, import-boundary validation, and
the full suite pass.

Allowed paths are declarations in this slice, not filesystem enforcement.
Non-bypassable path enforcement remains a future hook, sandbox, or wrapper
responsibility and must not be claimed by this version.
