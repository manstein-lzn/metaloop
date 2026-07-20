# MetaLoop Engineering Governance Migration Plan

Status: V2.1 cutover implemented

Document type: normative migration record

Last verified: 2026-07-20

## Previous State

The first governance slice lived only in the v1 Mission Capsule. At the same
time, V2 declared ContractRevision canonical for new work. The merged Skill
therefore instructed architecture Tasks to call a command that V2 correctly
disabled. The extracted CLI also retained keyword-based semantic inference even
though the canonical adaptive core had removed it.

## V2.1 Contract

- All new work uses Task and ContractRevision.
- Progressive Design remains conditional Skill intelligence.
- Optional governance is ContractRevision content, not a second state model.
- Stable inputs and managed outputs have different lifecycle semantics.
- Semantic change and adaptive decisions are explicit agent choices.
- V1 artifacts are read/migration input only.

## Cutover

1. Add the V2 governance schema and deterministic helper API.
2. Enforce it through contract lock, Attempt lifecycle, Evaluation, Review,
   acceptance, selected-task integrity, and RecoveryView.
3. Normalize valid legacy governance during `project migrate-legacy`.
4. Remove the duplicate keyword classifier from canonical CLI.
5. Rewrite the main Skill around one V2 path and move v1 details to a migration
   reference.
6. Add cross-feature behavioral tests rather than independent feature-only
   checks.
7. Regenerate and replace the complete installed Skill.

## Compatibility

Existing V2 contracts without governance remain valid. Existing v1 Capsules
remain readable and migratable. Callers that relied on keyword inference must
provide explicit semantic decisions; no active compatibility classifier is
retained.

## Removal Condition

The cutover is complete only when repository search finds no keyword classifier
on the active path, full tests pass, the vendored core matches canonical source,
and the installed Skill matches the repository package.
