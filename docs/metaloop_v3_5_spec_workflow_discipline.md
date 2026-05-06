# MetaLoop v3.5: Spec Discipline + Workflow Discipline

Last updated: 2026-05-04

v3.5 absorbs useful discipline from OpenSpec-style agree-before-build and Superpowers-style brainstorming/debugging gates without importing their code, CLIs, or runtime.

## Scope

This increment keeps the current main path intact:

```text
Co-Design -> MissionSpec -> MissionCapsule -> GoalContract -> Codex Execution -> VerificationResult -> SoftReviewDecision -> repair/redesign/complete
```

It does not add OpenSpec CLI, Superpowers runtime, recursive MetaLoop, or a new default worker pipeline.

## Co-Design Reviewer

`MissionSpecReviewer` now has conservative v3.5 findings:

- `scope_too_broad`
- `missing_non_goals`
- `missing_evidence_path`
- `weak_acceptance`
- `unclear_authority`
- `missing_tradeoff_review`
- `needs_decomposition`

The rule is intentionally asymmetric: high-risk or clearly broad missions can block, while Lite tasks are not blocked merely because they omit non-goals.

## Redesign Proposal Delta

`RedesignProposal` includes `contract_delta`:

- `added_scope`
- `removed_scope`
- `added_non_goals`
- `added_acceptance`
- `modified_acceptance`
- `removed_acceptance`
- `authority_delta`
- `evidence_delta`

The delta is proposal evidence only. MetaLoop does not mutate MissionSpec, MissionCapsule, GoalContract, scope, authority, or acceptance automatically.

`metaloop status --json` exposes the full delta. Plain `metaloop status` prints a compact delta summary when a redesign proposal exists. Resume still stops on `redesign_required`.

## Repair Discipline

Implementation repair remains contract-locked. Repair prompts and VerificationResult repair records include:

- `repair_attempt_index`
- root cause/hypothesis prompt requirements
- failed fix summary
- locked contract reminders

The first repair can be lightweight. The second repair prompt requires root cause and hypothesis. A third worker-fix request escalates to `redesign_required` instead of looping indefinitely.

## Domain Evidence Obligations

Domain profiles now carry evidence obligations:

- `engineering_development`: changed files, build/test/lint evidence when applicable, regression evidence for bugfix/public behavior changes.
- `algorithm_research`: assumptions, method, experiment or benchmark evidence, limitations.
- `codex_skill_creation`: SKILL.md, usage example, validation checklist.
- `deep_research`: source table, citation/provenance, freshness, claim support.

Most obligations are soft checks or evidence plan hints. Hard required evidence still fails verification; for example, engineering bugfix/public behavior work cannot become `completed_verified` without regression/build/test evidence.

## Prompt Pack v1

Prompt templates are documented in:

```text
prompts/co_design/discovery.md
prompts/co_design/brainstorm.md
prompts/run/soft_reviewer.md
prompts/run/repair.md
prompts/run/redesign.md
```

Each file includes metadata: version, purpose, input schema, output schema, and failure policy. Runtime prompt builders remain in code for now; no complex loader is introduced in v1.
