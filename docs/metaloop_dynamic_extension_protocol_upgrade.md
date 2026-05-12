# MetaLoop Dynamic Extension Protocol Upgrade

Date: 2026-05-08

## Goal

Upgrade the self-contained `$metaloop` Codex Skill from a generic VerificationSpec kernel into a lightweight protocol that lets agents design task-specific ExtensionSpec and VerificationSpec during design, while MetaLoop locks, executes, verifies, and audits those specs.

MetaLoop Core must stay small. It must not accumulate domain rules. Domain-specific rules are carried by ExtensionSpec / VerificationSpec and, later, domain extension packages.

## Non-Negotiable Architecture Boundary

```text
MetaLoop Core
  -> Mission Capsule, ExtensionSpec lock, VerificationSpec lock, state, ExecutionReport, VerificationResult, repair/redesign discipline, audit trail

Domain Extension / Task ExtensionSpec
  -> domain verification language, evidence types, risk checks, validator semantics, resource gates

Agent
  -> designs ExtensionSpec and VerificationSpec during design; explains risk philosophy and gates

MetaLoop Verifier
  -> executes only locked executable checks; does not trust worker self-report; does not weaken rules after execution
```

## Required Flow

```text
Design
  -> agent classifies task domain
  -> agent decides whether generic validators are enough
  -> if generic is insufficient, agent proposes a task-specific ExtensionSpec
  -> agent proposes a task-specific VerificationSpec
  -> agent marks every validator mode/severity

Review
  -> user/reviewer/MetaLoop checks risk coverage and known gaps

Lock
  -> Mission Capsule, ExtensionSpec, VerificationSpec, and review metadata are locked together
  -> hashes are recorded

Execute
  -> worker executes around locked capsule
  -> MetaLoop writes ExecutionReport

Verify
  -> MetaLoop validates capsule/spec/report hashes and schemas
  -> MetaLoop executes locked executable checks
  -> manual or unsupported blocking checks cannot be hard-verified

Failure
  -> repair if contract remains valid
  -> redesign/revision if task boundary or spec must change
```

## Data Objects

### ExtensionSpec

Describes the verification language for the task/domain.

Required minimum fields:

```json
{
  "schema": "metaloop.extension_spec",
  "version": "1.0",
  "domain": "generic",
  "purpose": "Generic local task verification.",
  "validator_types": [],
  "risk_checks": [],
  "review_questions": [],
  "known_gaps": [],
  "extension_hash": "sha256:..."
}
```

### VerificationSpec

Describes this exact task's completion gates.

Required minimum fields:

```json
{
  "schema": "metaloop.verification_spec",
  "version": "1.0",
  "domain": "generic",
  "extension": "generic",
  "extension_version": "1.0",
  "extension_hash": "sha256:...",
  "spec_hash": "sha256:...",
  "validators": [],
  "evidence_requirements": [],
  "resource_gates": []
}
```

### Validator Discipline

Every validator must support:

```json
{
  "type": "json_metric_gate",
  "mode": "executable",
  "severity": "blocking"
}
```

Allowed `mode`:

- `executable`: current kernel can execute it.
- `manual`: requires human/reviewer judgment.
- `unsupported`: important for the task but no current executor exists.

Allowed `severity`:

- `blocking`: unresolved/failed means not complete.
- `advisory`: reported as warning, not hard completion proof.

Verifier behavior:

```text
executable + blocking + failed -> failed
manual + blocking + delegatable -> review_required
manual + blocking + delegatable + approved review_result -> completed_verified
manual + blocking + delegatable + rejected/needs_changes review_result -> failed
manual + blocking + user authority -> human_acceptance_required
unsupported + blocking -> unsupported_verification_spec
advisory unresolved/failed -> warning, never hard proof
```

VerificationSpec validators must also be declared by the locked ExtensionSpec's
`validator_types`. Unknown validators cannot be smuggled into a generic spec. A
future or domain-specific validator must first appear in the task/domain
ExtensionSpec, then verification may classify it as manual, unsupported, or
implemented executable.

## Generic Validators

The bundled generic extension must support these executable validators:

- `file_exists`
- `command`
- `forbidden_path`
- `json_metric_gate`
- `json_field_exists`
- `file_contains`
- `artifact_hash`

The bundled generic extension must support these non-executable/manual protocols:

- `forbidden_claim`
- `resource_gate`

## Review Discipline

Task-specific extension specs must include risk coverage before lock:

- `risk_checks` or `review_questions` must be non-empty for non-generic domains.
- known gaps must be recorded and surfaced in VerificationResult.
- no validator may be silently upgraded from manual/unsupported to hard verified.
- delegatable manual gates are resolved only by `.metaloop/review_result.json`.
- review results must match the current capsule id, capsule revision, and
  VerificationSpec hash.
- reviewer role must be independent from the worker role.

## Revision Discipline

Overwriting a locked capsule is a revision, not a silent replacement.

Rules:

- `design --force` requires `--revision-reason` if a capsule exists.
- old capsule is archived under `.metaloop/revisions/`.
- new capsule increments `revision`.
- changing ExtensionSpec / VerificationSpec after failure requires a revision.

## Extension Package Shape

The skill must include a generic extension package so agents can discover the pattern:

```text
skills/metaloop/extensions/generic/
  profile.json
  verification_schema.json
  examples/basic.json
```

The kernel may only execute bundled generic validators for now, but the protocol must allow task-specific ExtensionSpec and VerificationSpec to be locked and classified safely.

## Acceptance Criteria

- intent-only design is rejected.
- generic design auto-generates ExtensionSpec and VerificationSpec.
- non-generic ExtensionSpec without risk checks/review questions is rejected unless explicitly allowed.
- ExtensionSpec tampering is rejected.
- VerificationSpec tampering is rejected.
- malformed or missing validator `mode` / `severity` is rejected before lock.
- validators outside the locked ExtensionSpec language are rejected before lock.
- declared but unimplemented executable blocking validator returns `unsupported_verification_spec`.
- declared delegatable manual blocking validator returns `review_required`.
- approved independent review result can resolve delegatable manual blockers.
- stale or worker-authored review result does not resolve `review_required`.
- declared user-authority manual blocking validator returns `human_acceptance_required`.
- advisory failed/unsupported validators appear in warnings.
- `json_field_exists`, `file_contains`, and `artifact_hash` work.
- `resource_gate requires_user_confirmation` blocks hard completion.
- `design --force` requires `--revision-reason` and archives previous capsule.
- local skill remains self-contained and passes skill validation.
- full test suite passes.
