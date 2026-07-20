# MetaLoop V2.1 Engineering Governance

Status: implemented V2-native vertical slice

Document type: normative specification

Last verified: 2026-07-20

## Objective

Prevent architecture, scope, and public-contract drift without creating a
second task system. V2 ContractRevision remains the only new-work contract;
governance is an optional content block for architecture-sensitive Tasks.

## Non-goals

- No Mission Capsule new-work path.
- No second persistence table or architecture copy under `.metaloop/`.
- No scheduler, watcher, daemon, agent pool, or project manager.
- No keyword inference of repair, extension, redesign, or pivot.
- No claim that `allowed_paths` is host-enforced isolation.

## Contract Shape

```text
governance
  schema = metaloop.v2.engineering_governance
  change_kind = repair | extension | redesign
  stable_inputs[] = role + path + sha256
  managed_outputs[] = role + path
  allowed_paths[]
  migration_plan = role + path + sha256 | null
```

Stable inputs are design facts that must not change during the Task. Managed
outputs are files the Task intentionally creates or changes; each must be exact
Attempt evidence before seal. This distinction allows legitimate redesign
without weakening baseline identity.

## Change Kinds

- `repair`: governing design and contracts remain correct.
- `extension`: behavior grows without silently changing existing authority or
  contract meaning.
- `redesign`: goal, ownership, state semantics, public contract, authority, or
  migration model changes. A locked migration plan is required.

The intelligent agent chooses explicitly. Code only validates the vocabulary.

## Lifecycle Gates

- Contract lock validates shape, paths, scope, and live stable-input hashes.
- Attempt start rejects stable-input drift.
- Seal requires every managed output as live, exact Attempt evidence.
- Verification rechecks governance before and after validators run.
- Review rechecks evidence and governance before recording authority.
- Acceptance rechecks governance and the complete evidence chain.
- Selected-task integrity reports post-acceptance drift.
- RecoveryView carries a compact governance summary and freshness signal.

## Migration

Valid v1 `engineering_governance` is normalized into V2 ContractRevision
governance. Invalid or drifted legacy governance cannot become active V2
authority and remains unbound migration metadata. V1 mutable commands fail
closed after the database exists.

## Ownership

- Project docs own architecture and module-contract prose.
- ContractRevision owns the locked task and governance envelope.
- Attempt owns execution checkpoints and evidence.
- Evaluation/Review own completion authority.
- `metaloop_core.engineering_governance` owns deterministic governance logic.
- Host hook/sandbox/wrapper owns non-bypassable filesystem enforcement.

## Acceptance

- Ordinary V2 contracts remain valid without governance.
- Governed contracts are created through the V2 `task contract` command.
- Stable drift fails at all relevant lifecycle gates.
- Managed outputs cannot seal without exact evidence.
- Governed v1 migration preserves valid governance.
- CLI and core never infer semantic routing from prose.
- Canonical and vendored core remain identical.
