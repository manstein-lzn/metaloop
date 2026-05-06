# MetaLoop Minimal v3: Codex Goal Governance

Last updated: 2026-05-04

## Constitutional Layer

This document describes the current minimal v3 implementation path.

The higher-level architecture constitution is:

```text
docs/mission_capsule_constitution.md
```

That document defines Mission Capsule, lifecycle, authority, evidence, acceptance, domain profiles, attempt memory, and the relationship between ITC/SCP/SKS/AMP.

Minimal v3 is a working slice of that constitution:

```text
MissionSpec
  -> MissionCapsule
  -> GoalContract
  -> Codex goal runtime
  -> ExecutionReport
  -> VerificationResult
  -> SoftReviewDecision
```

Future changes should preserve the Mission Capsule invariants while evolving this v3 path incrementally.

## Decision

MetaLoop v3 MVP is intentionally small:

```text
MissionSpec -> MissionCapsule -> GoalContract -> Codex goal runtime -> ExecutionReport -> VerificationResult -> SoftReviewDecision -> optional repair -> final VerificationResult -> MissionCapsule ledger/closure
```

MetaLoop does not try to become a second Codex. It does not micromanage tools, split every task into role-agent turns, or run a generic multi-agent runtime by default.

Codex owns execution. MetaLoop owns mission design and acceptance.

## Core Objects

### MissionSpec

Produced by `metaloop design`.

It captures:

- user intent
- deliverables
- constraints
- out-of-scope boundaries
- acceptance criteria
- workspace policy

Co-Design v2 normalizes MissionSpec toward later GoalContract and VerificationResult use:

- file-like deliverables get hard validators when possible
- path-based hard validators must target concrete repository paths; prose deliverables are never valid `file_exists` targets
- Co-Design extracts paths from deliverable sentences when possible, for example `Create docs/guide.md with examples` becomes `docs/guide.md`
- behavior phrases and concept pairs such as `tabs/newlines`, `input/output`, `before/after`, and `pass/fail` are not valid path targets
- directory targets must be explicit with a trailing `/`, for example `src/` or `tests/`
- non-machine-checkable work is marked as `llm_review` or final `manual` human acceptance
- `manual` is reserved for final user acceptance, not internal routing
- known task families set `context.domain_profile_id` for Capsule domain binding
- reviewer findings block or warn when MissionSpec is not ready for Capsule/GoalContract compilation
- requirement discovery still asks high-value follow-up questions
- brainstorm expansion makes the agent propose options, tradeoffs, risks, overlooked points, and MVP/V1/later routes
- selected Codex co-design agents are fail-fast: unavailable Codex, missing final message, invalid JSON, or unusable brainstorm output stops design instead of silently falling back to rule logic
- Spec Discipline v1 adds conservative agree-before-build checks for broad scope, missing non-goals, missing evidence path, weak acceptance, unclear authority, missing tradeoff review, and decomposition needs. High-risk or clearly broad missions can block; ordinary Lite tasks are not blocked merely because they omit non-goals.
- human design review is rendered as readable Markdown/Rich output, not just JSON
- interactive refinement uses compact structured design state plus unresolved questions and current draft
- contract lock happens only after explicit human approval in an interactive terminal; non-interactive/JSON modes auto-lock for script compatibility only when the reviewer has no blocking findings and brainstorm has no task-specific unresolved decisions

During and after design, MetaLoop writes Co-Design v2 process artifacts plus design-time contract previews:

```text
.metaloop/design_transcript.jsonl
.metaloop/design_draft.md
.metaloop/design_review.md
.metaloop/design_decisions.json
.metaloop/design_lock.json
.metaloop/design_capsule.json
.metaloop/design_goal_contract.json
```

The process artifacts record the design conversation and lock decision. The Capsule/contract previews prove contract readiness without pretending a run has started. The live run Capsule remains `.metaloop/mission_capsule.json`.

### GoalContract

Compiled from MissionCapsule, which is compiled from MissionSpec.

It is the Codex-facing task contract:

- objective
- purpose
- desired end state
- key tasks
- constraints
- forbidden actions
- acceptance criteria
- required execution report path

Important: GoalContract is a strong instruction to Codex, not a hard runtime guarantee. MetaLoop still verifies after execution. Runtime validators repeat the same path-target safety checks used during Co-Design, so historical or hand-written MissionSpecs with invalid path targets fail verification even if an executor creates a matching artifact.

### MissionCapsule

Compiled before execution and written to:

```text
.metaloop/mission_capsule.json
```

It is the canonical governance object for the run:

- locked mission charter
- authority contract
- acceptance contract and verification plan
- evidence plan
- domain profile
- append-only evidence ledger
- append-only attempt history
- decision ledger
- lifecycle state and closure outcome

The goal runtime updates the Capsule after execution with ExecutionReport evidence, VerificationResult evidence, SoftReviewDecision evidence, an AttemptRecord, and the final closure decision. Missing required evidence is a failed verification result, not a soft limitation.

Completed runs also write git-aware attempt history, without committing:

```text
.metaloop/attempts/<attempt_id>.json
```

The record includes the current commit ref when the workspace is in a Git repository, changed files, validation/result summary, and lessons. Runtime noise such as `.metaloop/`, `metaloop.mission.json`, `__pycache__/`, `.pyc`, and `.pyo` is filtered out of attempt changed files.

### ExecutionReport

Written by Codex after execution, usually at:

```text
.metaloop/execution_report.json
```

It records:

- completed / blocked / failed
- summary
- changed files
- commands run
- validation results
- evidence
- known limitations

Important: ExecutionReport is candidate evidence, not final truth.

DomainProfile evidence obligations are interpreted during verification. Engineering tasks should record changed files and applicable build/test/lint evidence; bugfix or public behavior changes require regression/build/test evidence. Algorithm research should record assumptions, method, experiment/benchmark evidence, and limitations. Codex skill creation should record SKILL.md, a usage example, and a validation checklist. Deep research should record source table, citation/provenance, freshness, and claim support when those obligations are in scope.

### VerificationResult

Produced by `metaloop verify`.

It classifies final status:

- `completed_verified`
- `completed_with_soft_acceptance`
- `completed_with_limitations`
- `completed_pending_human_acceptance`
- `failed`
- `blocked`

### SoftReviewDecision

Produced by the internal reviewer during `metaloop run`.

It is not human acceptance. It is an internal routing decision:

- `complete`
- `ask_worker_to_fix`
- `ask_architect_to_rethink`
- `ask_planner_to_replan`
- `ask_brainstormer_for_options`
- `fail`

The default goal runtime implements all routes. `ask_worker_to_fix` goes to a focused implementation repair prompt. `ask_architect_to_rethink`, `ask_planner_to_replan`, and `ask_brainstormer_for_options` call the corresponding focused agent for redesign guidance and then stop with a RedesignProposal. `fail` terminates the run as failed.

Current Repair / Redesign Capsule Semantics v1:

- `ask_worker_to_fix` is implementation repair only. It may fix files and update ExecutionReport, but it must not modify locked MissionSpec, MissionCapsule, GoalContract, scope, authority, or acceptance.
- repair attempts carry workflow discipline: `repair_attempt_index`, prompt requirements, failed fix summary, and repeated-repair root cause/hypothesis requirements. The first repair can be lightweight; the second prompt requires root cause and hypothesis; a third worker-fix request escalates to `redesign_required` instead of looping indefinitely.
- `ask_architect_to_rethink`, `ask_planner_to_replan`, and `ask_brainstormer_for_options` are contract-level redesign routes. They generate a `RedesignProposal`, write `.metaloop/redesign_proposal.json`, mark VerificationResult as failed with `redesign_required`, and move the Capsule to `redesign_required`.
- v1 does not automatically apply the proposal. Applying redesign requires a later explicit Capsule revision / revised MissionSpec flow.
- `fail` closes the Capsule as failed.

### RedesignProposal

Written when an internal reviewer decides worker repair would be the wrong tool.

It records:

- reviewer route
- reason
- why worker repair is insufficient
- proposed intent, acceptance, scope, and authority changes
- structured `contract_delta`: added/removed scope, added non-goals, added/modified/removed acceptance, authority delta, and evidence delta
- evidence references

RedesignProposal is proposal evidence, not an automatic contract mutation.

`metaloop status` includes redesign reason and contract delta summary in plain output, and exposes the full `contract_delta` in `--json`. `metaloop resume --mode goal` still stops on redesign_required rather than blindly rerunning the worker.

### Prompt Pack v1

Key prompt templates are also documented under:

```text
prompts/co_design/discovery.md
prompts/co_design/brainstorm.md
prompts/run/soft_reviewer.md
prompts/run/repair.md
prompts/run/redesign.md
```

Each prompt file has metadata for id, stage, version, purpose, input schema, output schema, failure policy, and required variables. The current implementation keeps code-native prompt builders as the runtime source of truth except for Co-Design brainstorm, which compiles from `prompts/co_design/brainstorm.md`, Co-Design discovery/interviewer, which compiles from `prompts/co_design/discovery.md`, focused redesign route guidance, which compiles from `prompts/run/redesign.md`, and soft review, which compiles from `prompts/run/soft_reviewer.md`.

### Prompt Compiler v3.6 Phase 0/1/2/3/4/5

Phase 0, Phase 1, Phase 2, Phase 3, Phase 4, and Phase 5 are now implemented. Phase 5 is intentionally narrow: only the run/soft_reviewer prompt was added after focused redesign route guidance.

- Phase 0 adds semantic baseline tests for the current hardcoded prompt builders.
- Phase 1 adds a read-only `metaloop.prompt_pack` loader/compiler for prompt md files.
- Phase 2 wires `_build_codex_brainstorm_prompt` / `CodexCoDesignBrainstormer` to `prompts/co_design/brainstorm.md` and injects MissionSpec, CoDesignDraft, and MissionSpecReview as fenced JSON.
- Phase 3 wires `_build_codex_interviewer_prompt` / `CodexCoDesignInterviewer` to `prompts/co_design/discovery.md` and injects `patch_mode`, `patch_mode_instruction`, and CoDesignDraft as fenced JSON.
- Phase 4 wires `build_focused_route_prompt` to `prompts/run/redesign.md` and injects route/role, MissionSpec, MissionCapsule, VerificationResult, and SoftReviewDecision as fenced JSON.
- Phase 5 wires `build_soft_review_prompt` to `prompts/run/soft_reviewer.md` and injects MissionSpec, GoalContract, VerificationResult, and the actual `SoftReviewDecision.model_json_schema(by_alias=True)` as fenced JSON.
- Prompt files now include `id`, `stage`, and `required_variables` metadata.
- The loader parses simple front matter, performs strict `{{var_name}}` replacement, rejects missing/empty variables and unresolved placeholders, and returns rendered text plus sha256.
- Co-Design brainstorm/discovery, focused redesign route, and soft reviewer prompt rendering remain fail-fast when required runtime state is missing or prompt pack rendering fails. `CodexSoftReviewer.review` converts soft reviewer prompt render errors into failed low-confidence reviews rather than crashing or falling back to hardcoded prompt text.

Runtime prompts otherwise still come from Python builders. The planned remaining migration order is:

```text
repair
```

The main goal prompt is intentionally deferred because it is the highest-blast-radius execution contract.

## CLI Shape

MVP user-facing commands:

```bash
metaloop design
metaloop compile
metaloop run
metaloop verify
metaloop list
metaloop show
metaloop resume
```

Near-term target:

```bash
metaloop design
metaloop run
metaloop status
metaloop verify
```

`compile/list/show/resume` can remain as advanced or diagnostic commands.

Current `metaloop run` behavior:

- `auto` mode is the default.
- If a mission file is discovered or passed and no explicit worker is requested, MetaLoop uses goal-style runtime.
- If a direct intent is passed or `--worker` is explicitly set, MetaLoop uses the legacy Kernel path.
- `--mode rigorous` forces the legacy multi-role pipeline.

## Runtime Boundary

Codex goal runtime should receive a compact work order: normal natural-language instructions, a compact MissionCapsule summary, the full GoalContract, and a minimal ExecutionReport field contract. Codex should retain its native autonomy:

- search the repository
- read files
- edit code
- run tests
- debug failures
- decide implementation steps

MetaLoop should not pass a long chat transcript or static RAG dump by default.

For goal-mode runs from a mission file, the MissionSpec `run_id` is currently treated as the stable contract/capsule id. `metaloop verify` prefers the latest runtime mission referenced by `.metaloop/run.json` when present, so a user can verify from the original mission path without hitting an ExecutionReport mission id mismatch.

Because Codex CLI `0.128.0` does not expose a non-interactive `codex goal` command, the current implementation uses one ordinary `codex exec` call as the goal-style runtime. The adapter boundary is intentionally isolated so a future Codex `/goal` API can replace transport without changing the MetaLoop contract objects.

Goal-style resume v1 is not Codex thread-level continuation. MetaLoop does not claim to reconnect to the exact prior Codex token context. Resume is structured:

- read `.metaloop/run.json`
- read MissionSpec, MissionCapsule, ExecutionReport, VerificationResult, and Codex event log when present
- skip rerun for terminal successful VerificationResult
- rerun goal runtime with an explicit reason when ExecutionReport is missing, verification failed/blocked, the run manifest is incomplete, or Capsule closure failed
- stop and ask for redesign when `.metaloop/redesign_proposal.json`, Capsule `redesign_required`, or VerificationResult `redesign_required` is present
- keep using MissionSpec / Capsule / structured artifacts as the durable context handoff

If Codex later exposes a stable thread continuation API, only the adapter/resume transport should change.

## Structured Filesystem

The current MVP writes a compact structured state under `.metaloop/`:

```text
.metaloop/
  mission.json
  design_transcript.jsonl
  design_draft.md
  design_review.md
  design_decisions.json
  design_lock.json
  design_capsule.json
  design_goal_contract.json
  mission_capsule.json
  goal_contract.json
  goal_prompt.md
  execution_report.json
  verification_result.json
  redesign_proposal.json
  attempts/
    <attempt_id>.json
  run.json
  runs/
    <run_id>/
      codex_events.jsonl
      run.json
```

These files are the operational state handoff. They are intentionally small and stable:

- `mission.json`: locked MissionSpec for the current run.
- `design_transcript.jsonl`: stage-level Co-Design v2 transcript, including discovery rounds, brainstorm, review, refinement decisions, and lock event.
- `design_draft.md`: user-readable current design draft.
- `design_review.md`: user-readable design review page with goal summary, product shape, deliverables, included/not included, route, acceptance, risks, and decisions.
- `design_decisions.json`: structured design decisions and unresolved questions.
- `design_lock.json`: explicit Co-Design v2 lock record linking the approved MissionSpec, design Capsule, and design GoalContract.
- `design_capsule.json` / `design_goal_contract.json`: Co-Design output preview for the Capsule-level contract before execution.
- `mission_capsule.json`: canonical runtime Mission Capsule. `metaloop run` updates it with final evidence/attempt/closure ledger.
- `goal_contract.json`: structured Codex-facing task contract.
- `goal_prompt.md`: actual prompt sent to Codex.
- `execution_report.json`: report Codex is required to write.
- `verification_result.json`: MetaLoop acceptance classification.
- `redesign_proposal.json`: explicit proposal for contract-level redesign; not applied automatically.
- `attempts/<attempt_id>.json`: git-aware attempt history record. It captures the current commit when available, dirty changed files, validation commands, reviewer route, failure mode, and lessons. MetaLoop does not auto-commit.
- `run.json`: pointers to the current structured artifacts.
- `codex_events.jsonl`: raw Codex runtime event stream for audit/debugging.

`metaloop status` reads these files and reports:

- mission intent and domain profile
- Capsule lifecycle, closure, evidence count, attempt count, and latest decision
- run manifest and latest Codex event summary
- VerificationResult status, hard/evidence counts, soft-review route
- redesign proposal state, route, and reason
- one concise next action

## Historical Attempt Memory

MetaLoop should not use a long chat transcript as operational memory. Current state is stored in structured files, while historical learning should come from Git-backed attempt history.

Git is the preferred history substrate because it is already optimized for exact, inspectable change history:

- `git log` locates previous attempts.
- `git show <commit>` inspects a specific attempt without changing the workspace.
- `git diff <commitA>..<commitB>` compares strategies and implementation changes.
- `git show <commit>:path/to/file` reads a historical file version without checkout or rollback.

Rollback is not required for an LLM agent to learn from a previous attempt. The agent can inspect history read-only through Git commands, then compile relevant lessons into the next context packet.

Each important attempt should eventually be recorded as both:

- a Git commit with a structured commit message
- an optional machine-readable AttemptRecord under `.metaloop/attempts/<attempt_id>.json`

Recommended commit message shape:

```text
metaloop: attempt <short objective>

Intent:
- What this attempt was trying to solve.

Hypothesis:
- Why this approach might work.

Changes:
- Main files or behavior changed.

Validation:
- Commands/checks run and their result.

Result:
- completed / failed / blocked / partially useful.

Failure or Limitation:
- What did not work, if anything.

Lesson:
- What future agents should preserve or avoid.

Next:
- Recommended next action.
```

Recommended AttemptRecord fields:

```json
{
  "schema": "metaloop.attempt_record",
  "version": "1.0",
  "attempt_id": "attempt_<id>",
  "commit": "<git-sha>",
  "mission_id": "<mission-id>",
  "intent": "",
  "hypothesis": "",
  "changed_files": [],
  "validation_commands": [],
  "validation_result": "",
  "reviewer_decision": "",
  "failure_mode": "",
  "lesson": "",
  "next_recommendation": ""
}
```

The context compiler should treat Git history as a referenceable evidence layer, not as text to dump wholesale into prompts. A future LLM call should receive only the relevant attempt summaries, commit refs, and diffs needed for the current decision.

## Verification Boundary

MetaLoop must not treat Codex completion as verified completion.

Verification is layered:

- hard validators: file exists, file contains, command, schema
- soft review: LLM-reviewable quality criteria
- evidence checks: report, logs, screenshots, changed files
- final human acceptance: subjective product/design judgment after internal work is complete

If a criterion cannot be checked by code, MetaLoop must classify it honestly instead of pretending it is verified.

Human acceptance is not an internal agent route. During an autonomous run, the reviewer/scheduler should decide whether to `complete`, send repair work to a worker, request architectural rethink, request replanning, request brainstorming, or fail. User acceptance happens after MetaLoop has completed its internal loop and produced a final VerificationResult.

Current minimal repair loop:

```text
Codex worker
  -> hard verification
  -> internal soft reviewer
  -> if route=ask_worker_to_fix: send one focused repair prompt to Codex
  -> verify again
  -> reviewer decides complete/fail
```

## What Is Not MVP

The following documents remain useful design principles, but they are not v3 MVP implementation scope:

- full Agent Message Protocol
- full Structured Context Protocol
- full Structured Knowledge System
- full Intent Transmission Contract
- generic WorkerBackend ecosystem
- recursive MetaLoop spawning
- default multi-agent rigorous pipeline
- explicit Codex tool allowlist

They can be introduced later only when a concrete bottleneck proves they are needed.

## Current Implementation State

Implemented now:

- `GoalContract`
- `ExecutionReport`
- `VerificationResult`
- MissionSpec to GoalContract compiler
- Codex-facing goal objective renderer
- `metaloop compile`
- `metaloop verify`
- `metaloop status`
- goal-style `metaloop resume --mode goal`
- `CodexExecGoalRuntimeAdapter`
- `metaloop run` auto mode defaults to goal-style runtime for mission files
- goal-mode mission files keep stable contract id semantics, and `metaloop verify` bridges original mission files to the latest runtime mission manifest
- compact goal prompt renderer for lower token overhead without weakening locked contract constraints
- `.metaloop/` structured run files
- `SoftReviewDecision`
- internal reviewer route schema
- one-step `ask_worker_to_fix` repair loop
- Prompt Compiler v3.6 Phase 0/1/2/3/4/5: semantic prompt builder tests, strict prompt pack loader, Co-Design brainstorm runtime migration, Co-Design discovery/interviewer runtime migration, run/redesign focused route migration, and run/soft_reviewer migration

Still pending:

- true programmatic Codex `/goal` adapter when Codex exposes one
- finer-grained resume stages for goal-style runtime
- staged runtime prompt migration after soft reviewer: evaluate repair
- main goal prompt migration is deferred

Current Codex CLI `0.128.0` exposes `/goal` through the interactive TUI, but `codex --help` does not expose a standalone non-interactive `goal` subcommand. Until a stable goal API/CLI exists, MetaLoop should keep the adapter boundary clean and avoid pretending that `/goal` is fully automated.
