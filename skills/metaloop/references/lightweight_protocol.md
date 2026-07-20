# MetaLoop Lightweight Protocol Reference

MetaLoop is Codex's task design and stable execution protocol layer.

For new work, MetaLoop v2 uses a SQLite-backed durable work graph:

```text
Project -> Task -> ContractRevision -> Attempt -> Evaluation
                              \-> DecisionEvent
RecoveryView is a freshness-checked projection.
```

This is still a lightweight protocol, not a runtime. SQLite supplies local
transactional truth and indexed bounded recovery; Codex still supplies all
understanding, execution, and strategy.

## Product Position

MetaLoop is Prompt-first for intelligence and code-backed for truth.

MetaLoop should preserve:

- deep Design
- generic Adaptive Goal Loop for repeated problem solving
- immutable ContractRevision
- durable `.metaloop/` artifacts
- content-bound Evaluation and independent Review
- repair/redesign/resume decisions
- a bundled lightweight kernel for one-click skill deployment
- persistent Codex thread agents when a project needs separate long-lived responsibilities

MetaLoop should avoid leading with:

- thick runtime frameworks
- large fixed multi-agent systems
- prompt-only discipline
- repeated one-shot `codex exec` calls as the default intelligence layer for complex projects
- code mechanisms that do not correspond to repeated real failures
- process-heavy prompts that make the model follow a long script instead of optimizing for the desired outcome

## Prompt Surface

The skill prompt should be outcome-first:

- define the target outcome
- define success and failure evidence
- define constraints and non-goals
- define stopping conditions
- let Codex choose the smallest adequate protocol shape

Keep mechanism details in references and artifacts. The main skill should not
read like a long operating manual. Use hard words such as `must` or `never`
only for true invariants: locked contracts, verification authority, forbidden
claims, safety/resource blockers, and artifact truth.

For tool-heavy tasks, give a short preamble before inspection or execution, then
act. For long tasks, give concise progress updates and record durable
observations as v2 DecisionEvents. Use `.metaloop/event_log.jsonl` only when no
v2 database exists; never split one workspace across both histories.

Use bounded inspection: read enough project context to design the contract and
verification gates, but stop when extra searching no longer changes scope,
acceptance, risk, or evidence.

## Skill Boundary

Skill can carry the system, but cannot alone enforce non-bypassable constraints.

Use this split:

```text
$metaloop skill
  -> entry, alignment, design discipline, action suggestions

Bundled scripts / schemas / validators
  -> deterministic checks, artifact writes, status, verification

hooks / sandbox / wrapper runtime
  -> stronger constraints when needed
```

Use prompts, playbooks, and examples for understanding, diagnosis, strategy, and next-plan decisions. Use bundled scripts, schemas, validators, and `.metaloop/` artifacts for locked state, verification, audit, and recovery. Do not add framework code when a small prompt protocol and durable artifact are enough.

## Minimal Contract Truth

A ContractRevision should be readable by both user and Codex. Keep it focused on:

- intent
- context
- design rationale
- constraints
- non-goals
- acceptance criteria
- forbidden paths
- evidence requirements
- verification plan
- optional governance refs and scope

It is not a full transcript.

Task lifecycle, active-Attempt, dependency, and acceptance-head state are stored
separately. The root Mission Capsule remains a v1-only artifact or migration
input. It is not writable canonical state after v2 initialization.

## Durable Attempts And Recovery

One Attempt is one strategy under one exact ContractRevision. It starts open,
accepts append-only checkpoints and evidence, and becomes immutable when
sealed. One Task may have at most one open Attempt. Task mutations require an
expected state version; stale writers fail rather than overwrite progress.

Before an Attempt, check RecoveryView freshness and exact-replay fingerprint.
After material progress, append a checkpoint. Before handoff or context
compaction, refresh RecoveryView. A new thread reads the Task/Contract and
dependency heads, active or latest Attempt, selected Evaluation/acceptance
chain, bounded current Project/Task decisions, and DecisionEvents after the
saved cursor. Current decisions remain present after the cursor advances.

Automated verification creates an Evaluation bound to the sealed Attempt hash.
Independent review creates another Evaluation bound to that exact Evaluation
hash. Completion follows one Task acceptance head and fails closed on stale
IDs, hashes, authority, ContractRevision, or verified artifact content.

## Six Control Gates

MetaLoop should stay as a critical-control layer around Codex, not an agent
runtime. The six gates are:

- Design Gate: clarify target, boundaries, evidence, and stopping conditions.
- State Checkpoint: write important state into `.metaloop/` after key actions.
- Verification Gate: use locked validators and evidence instead of worker
  self-report.
- Adaptive Loop: diagnose failed or partial attempts before retrying.
- Control Point: consume explicit `.metaloop/control/*.json` intent at safe
  points.
- Observation Surface: expose goal, plan, verification, blockers, context, and
  next action through read-only summaries.

Workers should apply these gates at safe points: before attempts, before
expensive work, after attempts, before completion claims, and before handoff.

## Legacy Context Checkpoints

V2 long tasks use RecoveryView and append-only Attempt checkpoints. A v1-only
workspace may keep compact Markdown recovery notes in:

```text
.metaloop/context/
```

The minimal files are:

- `resume_brief.md`: current goal, locked acceptance, best result, latest
  diagnosis, next plan, and read-first artifacts.
- `current_hypothesis.md`: the current most credible explanation and next test.
- `failed_attempts.md`: attempted directions that should not be repeated.
- `project_brief.md`: stable project facts, constraints, and key paths.

These files are not authoritative task truth and are not written after v2
initialization. Import or summarize useful legacy context into the V2 Task and
RecoveryView.

## Decision Discipline

When output is unsatisfactory, classify before executing:

- `repair`: correct contract, defective implementation
- `redesign`: incorrect/incomplete contract, scope, authority, or acceptance
- `resume`: incomplete work, direction still valid
- `complete`: verification passed and any explicitly required reviewer or user acceptance is satisfied or pending

Never let a worker repair silently mutate locked contract boundaries.

## Adaptive Goal Loop

MetaLoop's general method is not research-specific. Use the same loop for engineering, frontend, benchmark, research, operations, and paper reproduction tasks:

```text
Goal -> Plan -> Act -> Observe -> Evaluate -> Diagnose -> Decide -> Next Plan
```

The loop adds learning state to ordinary verification. Verification says whether the current result satisfies locked gates. Diagnosis says why it did or did not satisfy them and what the next plan should learn or improve.

Use this decision vocabulary for repeated attempts:

- `complete`: success criteria are satisfied.
- `continue`: goal remains valid; another high-signal attempt is needed.
- `repair`: implementation is defective; the target and strategy are still valid.
- `redesign`: the goal, acceptance, scope, or VerificationSpec is wrong or incomplete.
- `pivot`: keep the goal but change the strategy direction.
- `stop`: do not continue under current constraints.
- `escalate`: blocked by host permission, external policy, unavailable
  resource, or explicitly reserved user authority.

Domain extensions should define evidence types, metrics, thresholds, extractors, and risk rules. They should not define a separate domain-only loop.

## Deployment Shape

The skill should be useful immediately after copying/installing the skill folder. It must not require the target machine to have the MetaLoop repository installed as a Python package.

The portable minimum is:

```text
SKILL.md
references/lightweight_protocol.md
scripts/metaloop_kernel.py
lib/metaloop_core/
```

The thin bundled kernel calls the vendored canonical core. V2 owns
`.metaloop/metaloop.db`; v1 compatibility supports the minimal
`.metaloop/mission_capsule.json` and `.metaloop/verification_result.json` flow
only before v2 initialization or as read-only migration input. V1 mutable
commands fail closed in a v2 workspace.
Do not assume a repository-level command is installed in the target project.

In the MetaLoop repository, `metaloop_core` is the reusable V2 state and
verification backend for Task identity, immutable contracts, recoverable
Attempts, evidence, Evaluations, DecisionEvents, thread assignments, and
RecoveryViews. The Skill kernel remains self-contained for one-click deployment;
repository tests keep its vendored core identical to canonical source.

V1-only workspaces may still write Mission Capsule, ExecutionReport, and
VerificationResult compatibility artifacts before migration. They are not a
second new-work path and become read-only input once V2 exists.

The minimum V2 Design Gate is stricter than a plain prompt: intent alone is
insufficient. A locked ContractRevision should include rationale, explicit
non-goals, acceptance criteria, and executable verification unless authority is
explicitly delegated to a reviewer or reserved for the user.

## Persistent Agent Threads

For complex projects, MetaLoop should not make an external local runtime pretend to be a better Codex conversation. Codex agents should keep the natural conversation and project understanding. MetaLoop should provide protocol state.

The recommended shape is:

```text
interface thread: user conversation and project stewardship
design thread: requirement exploration and VerificationSpec design
worker thread: implementation against locked ContractRevision
reviewer thread: independent contract/evidence review
verifier/kernel: deterministic checks from locked VerificationSpec
```

In v1-only workspaces the bundled kernel records this in `.metaloop/threads.json`.
V2 stores thread-to-Task focus in canonical `thread_assignments` and exposes it
through `task assignments`. Neither surface is a scheduler.

Thread context is useful for intelligence and cost control, but it is not
operational truth. Multi-thread agents must synchronize through the canonical
v2 Task, Contract, Attempt, Evaluation, DecisionEvent, RecoveryView, and thread
assignment state.

First version rule: define and record roles before building automatic dispatch. Do not replace one-shot `codex exec` sprawl with a heavier scheduler until real usage demands it.

## Event Log

Long-running tasks need a compact audit trail between design and final
verification. V2 uses canonical DecisionEvents. V1-only workspaces instead use
the compatibility path:

```text
.metaloop/event_log.jsonl
```

Use events for observations, decisions, actions, blockers, handoffs,
verification notes, repairs, redesign notes, and general notes. In v2 every
mutation names its Task (or explicit Project scope).

Example:

```bash
python3 "$KERNEL" --workspace . event append \
  --task <task_id> \
  --type blocker \
  --agent worker \
  --summary "CUDA unavailable; full training cannot start." \
  --evidence "nvidia-smi failed" \
  --next-action "mark blocked or redesign resource gate"
```

Events are not operational authority. They do not replace a ContractRevision,
modify locked acceptance, or mark completion. They make long-task state
inspectable and resumable without forcing a complex scheduler.

## VerificationSpec

ExtensionSpec describes the task/domain verification language. VerificationSpec
describes this exact task's completion gates. In V2 they are immutable
ContractRevision content; Mission Capsule ownership is v1-only.

The bundled kernel supports the `generic` extension first:

- `file_exists`
- `command`
- `forbidden_path`
- `json_metric_gate`
- `json_field_exists`
- `file_contains`
- `artifact_hash`
- `forbidden_claim`
- `manual_acceptance`
- `resource_gate`

Agents may design an ExtensionSpec and VerificationSpec during the design phase, but workers must not weaken them after execution. The kernel records hashes over the locked extension/spec and rejects tampered specs during verification.

Each validator must classify its verification mode and severity:

- `mode=executable`: kernel can run the check.
- `mode=manual`: delegated reviewer judgment is required by default; user
  judgment is required only when explicitly reserved.
- `mode=unsupported`: the task needs the check, but this kernel has no executor yet.
- `severity=blocking`: unresolved means not complete.
- `severity=advisory`: record as warning, not hard proof.

Domain-specific extensions should grow beside this generic core instead of being hardcoded into MetaLoop Core. For a new domain, the agent should first design a task-specific ExtensionSpec, risk checks, review questions, and VerificationSpec. Manual or unsupported blocking checks must not be reported as `completed_verified`.

The extension package shape is:

```text
extensions/<domain>/
  profile.json
  verification_schema.json
  examples/
```

The current skill includes `extensions/generic/` as the reference package.

For metric-driven or research tasks, `file_exists` can prove that an artifact exists, but it cannot prove success. Lock JSON metric gates, baseline comparisons, resource gates, forbidden claims, attempt-count evidence, or blocking manual review before execution. If the core metric fails, the run may be useful evidence, but it is not goal success.
