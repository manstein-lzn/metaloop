---
name: metaloop
description: "Use when a local project task needs durable task history, deep or progressive design, structured acceptance, independent verification, repair/redesign decisions, task switching, or recovery across long Codex sessions."
---

# MetaLoop

MetaLoop keeps complex Codex work coherent across long sessions by making the
Task, locked contract, Attempts, evidence, decisions, acceptance chain, and
recovery state durable outside chat context.

This is a self-contained Codex Skill. Use `scripts/metaloop_kernel.py` for
state and checks; do not assume a separate `metaloop` command is installed.

## Operating Contract

```text
Prompt handles intelligence. Code handles truth.
Skill handles entry and alignment.
Bundled kernel / schema / validators handle checks and durable state.
Hooks, sandbox, or wrapper runtime handle stronger non-bypassable constraints when needed.
```

MetaLoop is skill-first, not prompt-only. Keep the prompt surface short and
outcome-first. SQLite is canonical operational truth.

## One Canonical Path

Use the v2 durable work graph for all new work:

```text
.metaloop/metaloop.db
  Project -> Task -> ContractRevision -> Attempt -> Evaluation
                                      -> DecisionEvent
  RecoveryView is derived and freshness-checked.
```

The bundled kernel is a thin adapter over vendored `metaloop_core`. Do not
implement protocol behavior separately in the script. JSON/Markdown under
`.metaloop/v2/` and status/dashboard output are rebuildable projections.

Root Mission Capsule, ExecutionReport, VerificationResult, adaptive, context,
routing, and thread files are v1 compatibility input only. Import an existing
v1 workspace with `project migrate-legacy`. Once the database exists, v1
mutable commands must fail closed rather than create a second truth. Read
`references/legacy_v1_compatibility.md` only when migration is actually needed.

## Six-Gate Model

MetaLoop remains a small control layer around Codex:

1. `Design Gate`: clarify outcome, boundaries, evidence, and stopping conditions.
2. `State Checkpoint`: persist Attempt progress and important decisions.
3. `Verification Gate`: let locked validators and evidence decide completion.
4. `Adaptive Loop`: diagnose failed or partial work before retrying.
5. `Control Point`: consume explicit external control intent at safe points.
6. `Observation Surface`: expose read-only status, blockers, and next action.

## User Burden

The user should be able to say only:

```text
Use $metaloop. I want to <goal>.
```

Do not require the user to name Tasks, ContractRevisions, Attempts,
VerificationSpecs, RecoveryViews, thread assignments, or governance fields.
Infer the smallest adequate shape. Ask only questions that change the target,
acceptance, cost, permissions, destructive risk, data access, or external
resources.

## First Response

For non-trivial work, give a short preamble, then perform bounded inspection:

- run `project status` when `.metaloop/metaloop.db` exists;
- otherwise inspect legacy state and decide whether to migrate it;
- read README/STATE/HANDOFF or equivalent entry documents;
- inspect only files needed to determine scope, acceptance, risk, and evidence;
- stop when more searching no longer changes the design or verification plan.

Before substantial execution, state the goal, success evidence, non-goals,
constraints, risks, stopping conditions, and whether one Task or a Task graph is
needed. Hide protocol mechanics from the user unless they are diagnosing the
protocol itself.

## Design Gate

Create or select one explicit Task and lock an immutable ContractRevision.
Mutable lifecycle state never belongs in the contract. Every mutation must name
its Task, Attempt, or Evaluation and use the current Task `state_version` where
compare-and-swap is required.

A useful contract contains:

- goal and rationale;
- non-goals and constraints;
- observable acceptance criteria;
- executable validators and any explicit review authority;
- evidence requirements and stopping conditions;
- optional V2 engineering governance for architecture-sensitive work.

Do not weaken locked acceptance after execution. Replace a defective contract
with a new ContractRevision and an explicit reason; never silently reinterpret
the old contract.

## Progressive Design Rule

Use Progressive Design for architecture and long-horizon work, not as ceremony
for every edit:

- derive a coherent target model and surface missing dimensions, risks, and
  choices;
- identify durable invariants that later slices must preserve;
- select the smallest end-to-end slice that tests current assumptions;
- define cohesive module ownership and explicit interfaces;
- record deliberate concessions and the evidence that should revisit them;
- prefer a representative project-native path as the first walking skeleton;
- advance only when current evidence justifies the next slice.

Each design response should contribute a new deduction, missing dimension,
risk, choice, or clearer structure. Summarize established context only when it
creates a more useful shared model.

## Optional V2 Governance

Use governance only for architecture, behavior, public-contract, migration, or
cross-module changes where silent design drift is a real risk. Ordinary local
repairs do not need it.

The agent must explicitly choose `repair`, `extension`, or `redesign`. Code may
validate that choice but must never infer it from prose.

Governance lives inside the ContractRevision:

- `stable_inputs`: governing documents or module contracts that must not drift;
- `managed_outputs`: files this Task is expected to create or change and attach
  as exact Attempt evidence;
- `allowed_paths`: declared implementation scope, not sandbox enforcement;
- `migration_plan`: a locked stable input required for `redesign`.

Create the block through the V2 contract command, for example:

```bash
python3 "$KERNEL" --workspace . task contract \
  --task <task_id> --expected-version <n> --file contract.json \
  --change-kind extension \
  --stable-input governing_document=docs/architecture.md \
  --stable-input module_contract=docs/module.md \
  --managed-output implementation=src/feature.py \
  --allowed-path src
```

For redesign, also pass `--migration-plan docs/migration.md`. Stable inputs are
rechecked at Attempt start, seal, verification, review, acceptance, and selected
Task integrity. Managed outputs must be live Attempt evidence before seal.
Read `references/v2_governance.md` for the complete shape and semantics.

## Task And Attempt Workflow

Set the kernel path relative to this Skill:

```bash
KERNEL="<skill_dir>/scripts/metaloop_kernel.py"
```

Core commands:

```bash
python3 "$KERNEL" --workspace . project init
python3 "$KERNEL" --workspace . project status
python3 "$KERNEL" --workspace . task create --title "<task>"
python3 "$KERNEL" --workspace . task contract --task <task_id> --expected-version <n> --file contract.json
python3 "$KERNEL" --workspace . attempt start --task <task_id> --expected-version <n> --plan "<plan>"
python3 "$KERNEL" --workspace . attempt record --attempt <attempt_id> --type checkpoint --payload-json '{"next":"<next>"}'
python3 "$KERNEL" --workspace . attempt evidence --attempt <attempt_id> --path <artifact>
python3 "$KERNEL" --workspace . attempt seal --attempt <attempt_id> --expected-version <n>
python3 "$KERNEL" --workspace . evaluate verify --attempt <attempt_id>
python3 "$KERNEL" --workspace . evaluate review --evaluation <evaluation_id> --decision approved --reviewer <reviewer>
python3 "$KERNEL" --workspace . evaluate accept --task <task_id> --evaluation <evaluation_id> --expected-version <n>
python3 "$KERNEL" --workspace . recover show --task <task_id>
python3 "$KERNEL" --workspace . recover write --task <task_id> --from-file resume.md
python3 "$KERNEL" --workspace . project integrity
```

Use one Task for one independently resumable goal. Use parent/dependency Tasks
when a branch has its own contract, evidence, or lifecycle. A repair child may
unblock or provide evidence to its parent but never completes the parent.

One Task may have at most one open Attempt. One Attempt is one strategy under
one exact ContractRevision. Append checkpoints after meaningful progress and
before likely context compaction. Record a concrete `retry_reason` before
repeating an exact sealed or aborted Attempt. Semantic similarity remains agent
judgment; code only blocks exact replay.

## Recovery And Task Switching

Recovery must be `fresh` before starting or resuming expensive work. If it is
stale, inspect its bounded delta events and refresh it. A fresh RecoveryView
contains the contract head, dependency heads, active/latest Attempt refs,
acceptance chain, current Task/Project decisions, and compact governance status.

Persistent threads may be assigned to explicit Tasks with `task assign` and
`task return`. Thread context is useful for intelligence but is not operational
truth unless recorded as a checkpoint or DecisionEvent. There is no hidden
scheduler or automatic agent pool.

## Verification And Authority

Verification runs the locked validators against one sealed Attempt and creates
an immutable Evaluation. Worker self-report is not evidence. Reviews approve
one exact Evaluation hash and therefore one exact Attempt hash.

Use strong validators where the claim warrants them: command tests, metrics,
schema checks, artifact hashes, non-regression checks, and forbidden paths.
Bare file existence and broad keyword checks are only smoke evidence.

`review_required` is delegatable to an independent reviewer. Use
`human_acceptance_required` only when the user explicitly reserves authority.
Every blocking authority must appear in one linear approved acceptance chain.
Do not start another Attempt when the Task is already `ready_to_accept`.

Evidence and governance are rechecked at seal, verification, review, and
acceptance. If any bound artifact or stable input drifts, fail closed.

## Adaptive Decisions

After failed or partial verification, record observation, evaluation,
diagnosis, an explicit decision, and the next plan before retrying:

- `complete`: locked success is satisfied;
- `continue`: another high-signal attempt is justified;
- `repair`: implementation is defective while the contract remains correct;
- `redesign`: goal, scope, authority, acceptance, or contract is defective;
- `pivot`: retain the goal but change strategy;
- `stop`: continuing is not useful;
- `escalate`: permissions, policy, resources, or reserved authority block work.

Only low-dimensional mechanical states may map automatically to `complete`,
`continue`, `redesign`, or `escalate`. Never route repair, redesign, or pivot by
matching words in diagnosis text.

## Observation And Control

Use read-only summaries for observation:

```bash
python3 "$KERNEL" --workspace . status
python3 "$KERNEL" --workspace . observe --format brief
python3 "<skill_dir>/scripts/metaloop_dashboard.py" --workspace . --scope root
```

The dashboard must not expose mutation routes. External control intent may be
written under `.metaloop/control/`, but a dashboard or observer must not
silently route work, approve resources, edit contracts, or activate workers.
`activate` remains an explicit one-shot compatibility utility, never an agent
brain, daemon, or watcher.

## Validation Discipline

- Run relevant tests, builds, type checks, metrics, or smoke tests.
- If validation cannot run, say why and record the blocker.
- Do not accept worker self-report as final evidence.
- Do not weaken locked acceptance after execution.
- If a blocking validator fails, say the target failed.
- Before handoff, checkpoint the Attempt or record a DecisionEvent and refresh
  RecoveryView.

## Hard Boundaries

- ContractRevision is new-work truth; Mission Capsule is migration input only.
- SQLite Task lifecycle, active Attempt, and acceptance head are canonical.
- ContractRevision, sealed Attempt, Evaluation, and DecisionEvent are immutable
  and content-bound.
- `default_task_id` and thread assignment are navigation only; explicit mutation
  subject always wins.
- V1 mutable artifacts never coexist with V2 canonical writes, except explicit
  external control intent.
- Project architecture prose stays in project documents; governance stores only
  roles, paths, hashes, and scope declarations.
- `allowed_paths` is not non-bypassable enforcement.
- Do not build a second state system, scheduler, vector memory, transcript
  store, project manager, or project-specific policy inside MetaLoop core.

## References

- `references/v2_governance.md`: optional ContractRevision governance.
- `references/legacy_v1_compatibility.md`: read/migrate legacy work only.
- `references/lightweight_protocol.md`: product and protocol boundaries.
- `references/prompt_first_code_backed.md`: intelligence/truth split.
