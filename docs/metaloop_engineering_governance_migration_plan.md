# MetaLoop Engineering Governance Migration Plan

Status: active migration plan

Document type: normative migration plan

Authority: governs the vNext cutover for explicit semantic decisions

Last verified: 2026-07-11

Exit condition: core and portable kernel accept only explicit semantic route
decisions, all tests and docs use the new contract, and no keyword classifier
remains on the active path

## Why This Is a Redesign

The engineering-governance envelope is an additive capability, but the same
slice removes existing keyword-based inference from public decision helpers.
That changes public API semantics and therefore must be treated as redesign,
not hidden inside an extension or repair.

## Old Contract

- `classify_dissatisfaction(feedback)` inferred repair, redesign, resume, or
  complete from words in free text.
- `decide_next()` and `diagnose_next()` could infer repair, redesign, or pivot
  from diagnosis and next-plan prose.

## New Contract

- Intelligent agents choose semantic decisions explicitly.
- Code validates the declared decision vocabulary.
- Code may map low-dimensional mechanical states to `complete`, `continue`, or
  `escalate`; it does not manufacture repair, redesign, or pivot from prose.
- Engineering changes declare `repair | extension | redesign` explicitly in a
  locked governance envelope.

## Cutover Steps

1. Add governance envelope validation to core and portable kernel.
2. Change semantic helper behavior to explicit validation or mechanical-only
   defaults.
3. Update every repository caller and test to pass semantic decisions
   explicitly.
4. Add negative tests proving keywords do not control routing.
5. Run core/portable parity, import-boundary, and full-suite tests.
6. Dogfood the redesign through a new Mission Capsule revision that binds this
   migration plan.

## Compatibility

Existing Mission Capsules without `engineering_governance` remain valid.
Callers that relied on keyword inference must migrate; no compatibility adapter
will preserve that unsafe semantic behavior. Invalid free-text input to
`classify_dissatisfaction` now fails explicitly.

## Removal Condition

The old behavior is removed when repository search and tests show no active
caller relying on keyword inference and the full suite passes. There is no
parallel legacy classifier after cutover.
