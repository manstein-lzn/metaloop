# MetaLoop Team Internal Preview Guide

Date: 2026-05-08

MetaLoop is ready for team internal preview as a Codex Skill. Treat this as a
design-first protocol layer for complex Codex work, not as a fully hardened
multi-agent platform.

## Recommended Distribution Format

Use a Codex install prompt as the primary distribution format.

Why:

- The team already uses Codex.
- Codex can adapt installation to each developer's machine.
- The skill is self-contained under `skills/metaloop/`.
- The installer can validate the skill and run a smoke test instead of asking
  users to copy files manually.

Primary entry:

- [codex_install_metaloop_skill.md](codex_install_metaloop_skill.md)

Secondary manual fallback:

```bash
git clone git@github.com:manstein-lzn/metaloop.git /tmp/metaloop-skill-source
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
rm -rf "${CODEX_HOME:-$HOME/.codex}/skills/metaloop"
cp -R /tmp/metaloop-skill-source/skills/metaloop "${CODEX_HOME:-$HOME/.codex}/skills/metaloop"
python3 "${CODEX_HOME:-$HOME/.codex}/skills/metaloop/scripts/metaloop_kernel.py" --workspace . status
```

Open a new Codex session after installation if `$metaloop` does not appear in
the available skills list.

## What To Tell Internal Users

Use `$metaloop` when the task needs:

- deep design before implementation
- explicit scope, non-goals, constraints, and acceptance criteria
- structured `ExtensionSpec` / `VerificationSpec`
- independent verification instead of trusting agent self-report
- repair/redesign/resume decisions for long or ambiguous work

Do not use `$metaloop` for tiny one-step edits where ordinary Codex is enough.

## Expected First Message

For an existing repository:

```text
Use $metaloop for this repository. First inspect the project deeply, then design
a Mission Capsule with an ExtensionSpec and VerificationSpec before execution.
Do not implement until the capsule and verification protocol are locked.
```

For a concrete task:

```text
Use $metaloop. I want to <task>.
```

The skill should infer the MetaLoop protocol shape, inspect project context,
start with design, ask only blocking questions, propose verification gates, and
avoid execution until the contract is clear. Do not make users learn MetaLoop
internals before they can use the skill.

## Preview Boundaries

MetaLoop currently provides:

- self-contained Codex Skill package
- bundled lightweight kernel
- `.metaloop/` Mission Capsule, ExecutionReport, and VerificationResult files
- locked `ExtensionSpec` and `VerificationSpec`
- adaptive loop, event log, thread registry, tick, outbox, relay, and routable
  job envelope support
- validator `mode` and `severity`
- generic executable validators for files, commands, JSON fields/metrics, text,
  hashes, and forbidden paths
- manual/resource gates that block hard completion
- revision archive for replaced capsules

MetaLoop does not yet provide:

- a fully hardened non-bypassable runtime
- production-grade domain extension packages for every field
- automatic trust in agent-designed VerificationSpec
- hidden daemon/watchers or automatic agent pools
- strong sandbox/hook enforcement in every host environment

For important work, review the proposed `VerificationSpec` before execution.

## Feedback We Want

Ask preview users to report:

- where design felt too heavy or too shallow
- where the VerificationSpec missed real completion criteria
- where the agent tried to execute before locking the capsule
- where repair vs redesign was unclear
- which domain-specific validators/extensions would be useful

## Release Positioning

Use this wording:

```text
MetaLoop v0.1 internal preview: a self-contained Codex Skill for design-first,
spec-locked, independently verified local project work.
```

Avoid claiming:

```text
Production multi-agent runtime.
Fully non-bypassable enforcement.
Complete domain verification ecosystem.
```
