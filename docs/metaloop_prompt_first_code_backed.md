# MetaLoop Prompt-First / Code-Backed Discipline

Date: 2026-05-09

V2 makes the code-backed boundary concrete through SQLite: identity, immutable
hash chains, CAS, uniqueness, event cursors, duplicate fingerprints, and
Recovery freshness are code truth. Goal understanding, Attempt planning,
diagnosis, semantic similarity, and next-plan choice remain prompt intelligence.

## Position

MetaLoop should not turn agent intelligence into a large Python framework.

Use this split:

```text
Prompt handles intelligence.
Code handles truth.
Examples transfer skill.
Validators build trust.
Kernel stays small.
```

Modern Codex agents are strong enough to do much of the understanding, diagnosis, strategy, and reflection work through prompt protocol. MetaLoop should use that strength instead of replacing it with brittle code.

## Prompt Responsibilities

Use prompts, skill instructions, playbooks, and examples for work that requires judgment:

- understanding the user's real goal
- exploring requirements and tradeoffs
- forming hypotheses
- designing VerificationSpec and domain extensions
- diagnosing failed or partial results
- interpreting observations
- deciding whether to continue, repair, pivot, redesign, stop, or escalate
- proposing the next high-signal plan
- explaining uncertainty and residual risk to the user

Keep those prompts outcome-first. Prefer describing the desired result,
evidence, constraints, and stopping conditions over prescribing a long fixed
procedure. Long procedural prompts should be split into references, examples,
or durable artifacts when the main skill surface becomes hard to scan.

These are intelligence tasks. Hardcoding them too early makes MetaLoop rigid and hard to maintain.

## Code Responsibilities

Use code only where durable truth, verification, and recovery matter:

- locking Task ContractRevision with ExtensionSpec / VerificationSpec
- validating schema and hashes
- writing Attempt evidence, Evaluation chains, DecisionEvents, RecoveryViews, and thread assignments
- running deterministic validators
- summarizing current workspace state
- preventing accidental artifact drift
- enabling resume and handoff

These are state and trust tasks. Leaving them only in prompt makes the system hard to audit and easy to drift.

## Examples Over Frameworks

For domain behavior, prefer examples and playbooks before code frameworks:

```text
extensions/<domain>/examples/*.json
references/<domain>_playbook.md
references/<domain>_reflection_template.md
references/<domain>_forbidden_claims.md
```

Only promote a pattern into code when repeated usage proves that it must be machine-checked, routed, or recovered.

## Schema-Light Rule

Schemas should define minimum durable fields, not the whole thought process.

Good durable fields:

- goal
- plan
- observation
- evaluation_status
- diagnosis
- decision
- next_plan
- evidence
- validator results

Keep rich reasoning in markdown notes, events, or agent messages unless code needs to inspect it.

## Avoid Code-First Drift

Do not add new Python modules just because a prompt says something important. Add code only when at least one is true:

- the value must persist across sessions
- validators need to inspect it
- status/resume needs to route on it
- reviewers need an audit trail
- multiple agents need a shared handoff artifact

Otherwise, improve the prompt protocol or add an example.

## Outcome-First Skill Surface

The main `$metaloop` skill should optimize for a strong Codex interaction:

- short preamble before tool-heavy work
- bounded project inspection
- clear success and failure evidence
- explicit stopping conditions
- validation after changes
- repair/redesign/pivot/stop decisions after failed verification
- only blocking questions to the user

Details such as ContractRevision fields, job envelopes, relay mechanics, and
validator schemas belong in references or generated artifacts unless they are
needed in the first response.

## Relationship To Current Core

Current `metaloop_core` already owns the small code-backed truth layer:

- Project / Task / ContractRevision
- ExtensionSpec / VerificationSpec content
- Attempt checkpoints and evidence
- Evaluation / Review chain
- DecisionEvents and RecoveryView
- Thread assignments
- Routable work-unit schemas
- Pure router decisions
- One-shot tick and relay results

Do not keep adding report types by default. Use the existing loop unless a new state object has a clear verification or recovery role.

## Acceptance

MetaLoop is on track when:

- Codex agent remains the main intelligence
- skill prompt gives strong behavioral protocol
- kernel state is small and durable
- validators remain deterministic
- domain behavior grows through examples first
- core stays domain-neutral
- failures produce observation, diagnosis, and next-plan continuity
- the codebase gets simpler to reason about, not larger by reflex
