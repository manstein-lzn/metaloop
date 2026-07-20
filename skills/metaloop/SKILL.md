---
name: metaloop
description: "Use when a local project task needs MetaLoop's lightweight protocol: deep design before execution, structured acceptance, independent verification, repair/redesign/resume decisions, long-task feedback, or skill-first but code-backed task governance around Codex."
---

# MetaLoop

MetaLoop stabilizes complex Codex work by making Tasks, locked success
contracts, execution attempts, evidence, decisions, and recovery state durable
outside chat context.

This is a self-contained Codex Skill. Use `scripts/metaloop_kernel.py` for
state and checks; do not assume a separate `metaloop` command is installed.

## Operating Contract

```text
Prompt handles intelligence. Code handles truth.
Skill handles entry and alignment.
Bundled kernel / schema / validators handle checks and state.
Hooks, sandbox, or wrapper runtime handle stronger non-bypassable constraints when needed.
```

MetaLoop is skill-first, not prompt-only. Keep the prompt surface short and
outcome-first; use `.metaloop/` artifacts for durable truth.

## V2 Canonical State

Use the v2 durable work graph for new work:

```text
.metaloop/metaloop.db
  Project -> Task -> ContractRevision -> Attempt -> Evaluation
                                      -> DecisionEvent
  RecoveryView is derived and freshness-checked.
```

SQLite is canonical operational truth. JSON/Markdown under `.metaloop/v2/`
and dashboard/status output are rebuildable read-only projections. The bundled
kernel is a thin adapter over vendored `metaloop_core`; do not implement
protocol behavior separately in the script.

Existing root-level Mission Capsule, ExecutionReport, VerificationResult,
Adaptive Loop, and context files remain supported before v2 initialization or
as read-only migration input. Import them with `project migrate-legacy`; once
the database exists, v1 mutable commands must fail closed rather than create a
second truth. Legacy approval is bound only after v1 content validation and a
fresh rerun of the locked validators; otherwise it remains `legacy_unbound`.

## Six-Gate Model

MetaLoop is not an agent runtime. Codex is responsible for understanding,
creation, search, coding, experiments, interpretation, and strategy. MetaLoop
provides six lightweight control points:

1. `Design Gate`: clarify goal, non-goals, constraints, evidence, success, and
   stopping conditions before substantial execution.
2. `State Checkpoint`: preserve important observations, decisions, execution
   evidence, adaptive iterations, and context checkpoints in `.metaloop/`.
3. `Verification Gate`: locked validators and evidence decide completion; do
   not accept worker self-report.
4. `Adaptive Loop`: after failure or partial progress, record observation,
   evaluation, diagnosis, decision, and next plan before retrying.
5. `Control Point`: read explicit `.metaloop/control/*.json` intent at safe
   points; do not silently approve resources or mutate locked contracts.
6. `Observation Surface`: keep status visible through read-only summaries,
   events, verification, context checkpoint health, and pending controls.

## User Burden Rule

The user should be able to say only:

```text
Use $metaloop. I want to <goal>.
```

Do not require the user to ask for Mission Capsules, VerificationSpecs,
Adaptive Loops, blackboards, dispatch maps, job envelopes, tick, relay, or role
decomposition. Infer the smallest adequate protocol shape, explain it in plain
project terms, and ask only questions that change the target, acceptance,
cost, data access, external resources, destructive risk, or permissions.

## First Response

For non-trivial work, give a short preamble before tool use:

```text
I will inspect the current MetaLoop state and the relevant project context,
then propose the goal contract and verification gates before execution.
```

Then do a bounded inspection:

- run `project status` when `.metaloop/metaloop.db` exists
- otherwise inspect legacy `.metaloop/` state and decide whether to migrate it
- check `.metaloop/` status, thread registry, and recent events when present
- read README/STATE/HANDOFF or equivalent project entry docs when present
- inspect only files needed to understand the task surface
- continue searching only when a missing fact affects scope, acceptance, risk,
  or verification
- write important long-task discoveries as task/project DecisionEvents when v2
  exists; use `.metaloop/event_log.jsonl` only in a v1-only workspace

Do not stall in open-ended research. Stop inspection when you can state a
defensible goal, non-goals, constraints, risks, evidence, and verification plan.

## Design Output

Before execution, produce a plain-language design that answers:

- Goal: what outcome is being pursued?
- Success: what observable result proves enough progress or completion?
- Non-goals: what should not be changed or claimed?
- Constraints: what limits cost, time, data, permissions, resources, or scope?
- Evidence: what artifacts, metrics, commands, tests, or review notes will be
  used?
- Stopping conditions: when should Codex complete, continue, repair, redesign,
  pivot, stop, or escalate?
- Protocol shape: `single_node`, `multi_thread`, or `routable_work_units`,
  chosen by Codex, not the user.

For v2, create or select one Task and lock an immutable ContractRevision. Do
not place mutable lifecycle state inside the contract. Mutating operations must
name their Task/Attempt/Evaluation subject and use the current Task
`state_version` for compare-and-swap.

Lock the corresponding v2 ContractRevision with the bundled kernel before
implementation when the task is substantial or verification matters. Use the
Mission Capsule and VerificationSpec only in a v1-only workspace.

## Protocol Shape

Use the smallest shape that preserves correctness and recovery:

- `single_node`: one Mission Capsule, one ExecutionReport, one
  VerificationResult, and one Adaptive Goal Loop are enough.
- `multi_thread`: several persistent Codex threads help, but one workspace
  truth remains authoritative through `.metaloop/`.
- `routable_work_units`: separate responsibilities or workspaces need
  `job_envelope.json`, `global_blackboard.json`, outbox records, `tick`, and
  `relay`.

Do not use routable work units just because a task is large. Use them only for
real responsibility isolation, cross-workspace handoff, hard metric gates,
different resource profiles, or strong context isolation.

## Kernel Use

Set the kernel path relative to this skill:

```bash
KERNEL="<skill_dir>/scripts/metaloop_kernel.py"
```

Useful commands:

```bash
python3 "$KERNEL" --workspace . project init
python3 "$KERNEL" --workspace . project status
python3 "$KERNEL" --workspace . task create --title "<task>"
python3 "$KERNEL" --workspace . task create --title "<repair>" --parent-task <task_id> --spawned-by-event <event_id>
python3 "$KERNEL" --workspace . task contract --task <task_id> --expected-version <n> --file contract.json
python3 "$KERNEL" --workspace . task assignments
python3 "$KERNEL" --workspace . attempt start --task <task_id> --expected-version <n> --plan "<plan>"
python3 "$KERNEL" --workspace . attempt record --attempt <attempt_id> --type checkpoint --payload-json '{"next":"<next>"}'
python3 "$KERNEL" --workspace . attempt evidence --attempt <attempt_id> --path <artifact>
python3 "$KERNEL" --workspace . attempt seal --attempt <attempt_id> --expected-version <n>
python3 "$KERNEL" --workspace . evaluate verify --attempt <attempt_id>
python3 "$KERNEL" --workspace . evaluate review --evaluation <evaluation_id> --decision approved --reviewer <reviewer>
python3 "$KERNEL" --workspace . evaluate accept --task <task_id> --evaluation <evaluation_id> --expected-version <n>
python3 "$KERNEL" --workspace . recover show --task <task_id>
python3 "$KERNEL" --workspace . recover write --task <task_id> --from-file resume.md
python3 "$KERNEL" --workspace . event list --task <task_id> --limit 20
python3 "$KERNEL" --workspace . event show --event <event_id>
python3 "$KERNEL" --workspace . project export
python3 "$KERNEL" --workspace . project integrity

# read-only/shared surfaces
python3 "$KERNEL" --workspace . status
python3 "$KERNEL" --workspace . threads status
python3 "$KERNEL" --workspace . observe --scope root --json
python3 "$KERNEL" --workspace . observe --format brief
python3 "<skill_dir>/scripts/metaloop_dashboard.py" --workspace . --scope root
python3 "$KERNEL" --workspace . control write --type halt --reason "<why>"

# v1-only mutable compatibility commands; disabled after project init/migration
python3 "$KERNEL" --workspace . design ...
python3 "$KERNEL" --workspace . run --command "<command>" --evidence "<note>"
python3 "$KERNEL" --workspace . verify
python3 "$KERNEL" --workspace . review record --decision approved --reviewer "<reviewer>" --evidence ".metaloop/verification_result.json"
python3 "$KERNEL" --workspace . adaptive record ...
python3 "$KERNEL" --workspace . event append ...
python3 "$KERNEL" --workspace . context init
python3 "$KERNEL" --workspace . context status --json
python3 "$KERNEL" --workspace . context write --file resume_brief.md --content "<markdown>"
python3 "$KERNEL" --workspace . tick --envelope job_envelope.json
python3 "$KERNEL" --workspace . relay --dispatch-map dispatch_map.json
python3 "$KERNEL" --workspace . activate --root . --worker-command "<explicit command>"
```

Intent alone is not enough to lock a capsule. Include rationale, non-goals,
acceptance, and executable validators, or make manual-only review explicit.

For metric, benchmark, research, promotion, or quality-breakthrough tasks,
`file_exists` is not enough. Add metric gates, baseline comparisons, resource
gates, forbidden claims, attempt evidence, or blocking manual review.

For research, benchmark, reproduction, paper-claim, promotion, or leaderboard
claims, use `review_required` by default for final claim validation and prefer
an independent Codex reviewer thread unless the user explicitly opts out.

Validator quality ladder:

- Strong: metric gates, schema/field checks, command tests, artifact hashes,
  non-regression checks, official evaluator output, forbidden path/claim gates.
- Weak: bare `file_exists` and broad `file_contains`; use them only as smoke
  checks or pair them with stronger evidence.
- Not evidence: worker self-report, chat claims, or keyword presence without a
  locked artifact or command behind it.

Blocking review may require one or both authorities:

- `review_required`: quality, evidence, claim, or domain judgment can be
  delegated to an independent Codex reviewer. The worker may not self-approve;
  a reviewer must inspect locked evidence and record the outcome with
  `evaluate review` over the exact v2 Evaluation.
- `human_acceptance_required`: user-only authority is required only when the
  user explicitly reserves that authority in the locked contract. In goal mode,
  MetaLoop protocol authority is delegated to Codex agents by default; do not
  ask the user for ordinary MetaLoop protocol approvals, resource reviews, or
  final claim reviews unless the task exceeds the user's Codex/tool sandbox
  permissions or the user explicitly opts back into approval.

For observability, prefer read-only summaries from `.metaloop/` artifacts. For
control, write explicit intent files under `.metaloop/control/`; do not make a
dashboard or observer silently route work, approve resources, or mutate locked
contracts.

The bundled dashboard is read-only. It serves `observe --format brief` style
summaries in a browser and must not expose endpoints that write controls,
activate workers, route envelopes, or edit artifacts.

`activate` is an optional one-shot scanner, not an agent brain, daemon, or
watcher. Use it only when an explicit worker command is already chosen. It may
check envelopes, leases, and pending controls, write `activation_result.json`,
and exit; it must not design tasks, call Codex by itself, interpret metrics, or
change locked contracts.

For v2 long tasks, keep the Task RecoveryView current enough that a new Codex
thread can resume without reading the full transcript. V1-only workspaces may
use `.metaloop/context/resume_brief.md`. Recovery notes are compact projections,
not a second memory system.

For v2 Tasks, prefer `recover show` and `recover write`. Recovery must be
`fresh` before starting or resuming expensive work. An open Attempt carries its
own append-only checkpoints, so context compaction during execution does not
erase the current plan, completed actions, evidence, or next step. If Recovery
is stale, read its bounded delta events and refresh it before proceeding.

Before starting an Attempt, compute the durable fingerprint from its locked
contract, normalized plan, input snapshot, and relevant configuration. Do not
repeat an identical sealed/aborted Attempt unless a concrete `retry_reason` is
recorded. Semantic similarity remains an agent judgment informed by prior
DecisionEvents; do not claim perfect automatic duplicate detection.

Safe-point discipline: before an attempt, resolve the explicit Task, check its
state version, dependencies, controls, recovery freshness, and duplicate guard;
before expensive work, honor resource/control gates; after an attempt, write
evidence, verify, and record adaptive diagnosis; before completion, rely on
the exact immutable acceptance chain; before handoff, append an Attempt
checkpoint or DecisionEvent and refresh RecoveryView.

If verification returns `review_required`, do not ask the user by default.
Register or use an independent Codex reviewer thread when available, have it
inspect the ContractRevision, sealed Attempt, Evaluation payload, metrics, and
claimed conclusions, then append `evaluate review` to that exact Evaluation.
Only ask the user when reviewer independence is impossible, the host tool
permission is unavailable to Codex, or the locked contract explicitly reserves
user authority.

`.metaloop/` is local operational state and should normally be gitignored in
target projects. Keep summaries compact, archive only when useful, and do not
commit noisy revisions or transient event logs unless the team explicitly wants
an audit trail in git.

## Validation Discipline

Verification is part of the prompt, not an afterthought.

- Run relevant tests, commands, builds, type checks, metric checks, or smoke
  tests after changes when available.
- If validation cannot run, say why and record the blocker.
- Do not accept worker self-report as final evidence.
- Do not weaken locked acceptance after execution.
- If a hard metric gate fails, say the target failed.
- If evidence is missing or ambiguous, do not claim completion.

## Stopping Conditions

After each attempt, classify the state before acting:

- `complete`: locked verification passed and any required reviewer or user
  authority gate is satisfied or explicitly pending.
- `continue`: the goal is valid and another high-signal attempt is justified.
- `repair`: the contract is right; implementation is defective.
- `redesign`: scope, acceptance, authority, or VerificationSpec is wrong or
  incomplete.
- `pivot`: the goal remains, but the strategy direction should change.
- `stop`: continuing under current constraints is not useful.
- `escalate`: host permission, external policy, unavailable resource, or
  explicitly reserved user authority blocks progress.

Failed or partial verification must feed observation, evaluation, diagnosis,
decision, and next plan before another attempt.

## Hard Boundaries

- ContractRevision is v2 task truth; Mission Capsule is the v1 compatibility
  contract. Chat history is never operational state.
- Task lifecycle, active Attempt, and acceptance head are canonical SQLite
  state and must use compare-and-swap updates.
- ContractRevision, sealed Attempt, Evaluation, and DecisionEvent records are
  immutable and content-bound.
- A Review approves one exact Evaluation hash, which resolves to one exact
  sealed Attempt hash. It never approves the current workspace generically.
- Attempt evidence must still match its recorded hashes at seal, verification,
  and acceptance. `project integrity` checks live evidence for the default Task.
- Every blocking authority listed by the verification Evaluation must appear
  as an approved overlay in one linear acceptance chain.
- One Task may have at most one open Attempt. Child Task completion may unblock
  or provide evidence to its parent, but never completes the parent implicitly.
- `default_task_id` and thread assignment are navigation/default scope only;
  explicit mutation subject always wins.
- A fresh RecoveryView includes dependency heads, the resolved acceptance
  chain, and bounded supersession-resolved Task/Project decisions. Delta events
  alone are not long-term memory.
- `ready_to_accept` means accept the candidate Evaluation; never start another
  Attempt just because the latest decision string is `approved`.
- Persistent thread context is useful but not authoritative unless summarized
  into `.metaloop/` artifacts.
- `resume_brief.md` is recovery context, not task truth; it must point back to
  locked artifacts and evidence.
- Safe-point checks are a worker discipline, not a hidden scheduler.
- ExtensionSpec and VerificationSpec are locked with the Mission Capsule and
  carry hashes.
- Verification requires a valid ExecutionReport.
- Manual or unsupported blocking validators cannot become hard verified
  completion. Delegatable manual review is `review_required`; user authority is
  `human_acceptance_required`.
- Replacing a locked capsule requires a revision reason and archives the
  previous capsule.
- V1 root artifacts are never writable alongside a v2 database except for
  explicit external control intent files.
- Do not build a parallel state system outside `.metaloop/`.
- Do not store project-specific tasks, datasets, metrics, or business rules in
  this skill or in MetaLoop core.

## References

- `references/lightweight_protocol.md`: protocol details and skill boundary.
- `references/prompt_first_code_backed.md`: prompt-first / code-backed product
  discipline.
- Project docs, when present: `README.md`, `STATE.md`, `HANDOFF.md`,
  `docs/metaloop_six_gate_model.md`, `docs/metaloop_context_checkpoints.md`,
  `docs/metaloop_design_autonomy.md`, and
  `docs/metaloop_routable_work_units.md`.
