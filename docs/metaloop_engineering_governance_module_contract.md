# Engineering Governance Module Contract

Status: active V2.1 module contract

Authority: `metaloop_core.engineering_governance`

Last verified: 2026-07-20

## Responsibility

Own deterministic validation, legacy normalization, live stable-input checks,
managed-output evidence requirements, and compact summaries for optional V2
ContractRevision governance.

## Public API

```text
# V2
build_v2_governance(...)
validate_v2_governance(payload)
verify_v2_governance(workspace, payload, evidence_paths, require_managed_outputs)
summarize_v2_governance(workspace, payload)
normalize_legacy_governance(payload)

# V1 read/migration compatibility
build_locked_file(workspace, ref)
validate_engineering_governance(payload)
verify_engineering_governance(workspace, payload)
```

## Owned State

No independent persistence. V2 governance is immutable ContractRevision
content. V1 governance exists only in a legacy Mission Capsule before migration.

## Dependencies

- Python standard library.
- Leaf constants from `metaloop_core.schemas`.

The module must not depend on durable storage, CLI, verification, routing,
agents, product-specific packages, or semantic classifiers.

## Invariants

- Every path is safe and workspace-relative.
- Stable-input hashes are exact file-byte hashes.
- Managed outputs fall under an allowed path and become exact Attempt evidence.
- Change classification is explicit and never inferred from prose.
- Redesign requires a stable migration plan.
- Validation is deterministic and has no writes.
- Legacy normalization preserves valid governance without retaining a second
  active state model.

## Verification

Unit tests cover shape, path escape, drift, scope, redesign, legacy
normalization, and summaries. Durable integration tests cover contract lock,
Attempt start/seal, verification, review, acceptance, integrity, RecoveryView,
and migration. Skill-kernel tests cover V2 CLI construction.
