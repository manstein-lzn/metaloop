# Engineering Governance Module Contract

Status: active module contract

Document type: normative module contract

Authority: `metaloop_core.engineering_governance` and its portable-kernel mirror

Last verified: 2026-07-11

## Responsibility

Own deterministic validation of the small engineering-governance envelope and
verification of its workspace-local document hashes.

## Public API

```text
build_locked_file(workspace, ref) -> {ref, sha256}
validate_engineering_governance(payload) -> list[str]
verify_engineering_governance(workspace, payload) -> list[str]
```

## Owned State

No independent state. The module validates the `engineering_governance` value
stored in the locked Mission Capsule.

## Allowed Dependencies

- Python standard library only.
- Leaf constants from `metaloop_core.schemas`.

## Forbidden Dependencies

- Verification, routing, relay, activation, thread, or observation modules.
- Product-specific packages or MissionForge.
- Agent/model calls or semantic classifiers.

## Invariants

- Refs are non-empty, workspace-relative, and cannot escape the workspace.
- Hashes are computed from exact file bytes.
- Change classification is explicit, never inferred.
- Redesign requires a migration plan.
- Validation is deterministic and has no writes.

## Independent Verification

- Unit tests cover valid envelopes, missing fields, path escape, redesign
  requirements, and content drift.
- Skill/core parity covers one successful governed task and one drift failure.

## Shipped Reality

The module is implemented without persistence or product dependencies. Capsule
loading invokes it before execution and verification. Its portable-kernel
mirror is intentionally limited to the same envelope and is covered by parity
tests.
