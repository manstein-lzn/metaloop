# MetaLoop 最终架构与升级开发规范

Status: design baseline for the final clean cut

Audience: MetaLoop core maintainers, Skill maintainers, and future upgrade
implementers

This document is the implementation contract for the final MetaLoop shape. It
absorbs the remote engineering-governance and Progressive Design work, the
durable Task history work, and the workspace-alignment conclusions from the
latest architecture discussion. It intentionally does not preserve V1/V2 as
active compatibility products because MetaLoop has no formal external users.

## 1. Executive Decision

MetaLoop is a lightweight, Git-backed Codex work protocol and control layer.
It is not a project-management product, agent runtime, scheduler, transcript
store, or Git client UI.

The protocol connects four responsibilities:

```text
Codex / Skill
  -> understands, designs, implements, diagnoses, and chooses strategy

MetaLoop / SQLite
  -> preserves intent, task history, recovery, evidence, and authority

Git worktree
  -> proves mechanical project changes and workspace identity

Validators / Review
  -> decide whether one exact Attempt satisfies one exact ContractRevision
```

The final architecture has one canonical protocol path and one source of
truth for each concern:

```text
Project / Workspace
  -> Task graph
  -> ContractRevision
  -> Attempt + Checkpoint + Evidence
  -> DecisionEvent
  -> Evaluation + Review
  -> RecoveryView
```

SQLite is canonical protocol truth. Git is canonical workspace-change truth.
Project documents remain the source of architecture and domain prose. No layer
copies another layer's authority.

## 2. Product Capabilities

MetaLoop is useful because it improves how an Agent works, not because it
merely records files. The final product must preserve these capabilities.

### 2.1 Design intelligence

For a non-trivial request, the Skill makes Codex inspect the project, establish
the target model, identify missing dimensions, ask only blocking questions, and
propose observable success and stopping conditions.

### 2.2 Progressive Design

For architecture and long-horizon work, design depth and implementation breadth
are independent. Codex may develop a coherent long-term model while locking the
smallest end-to-end slice that tests current assumptions.

The design discipline is:

1. Expand the goal into a target model.
2. Separate durable invariants from current scope.
3. Assign cohesive module ownership and explicit interfaces.
4. Record deliberate concessions and revisit evidence.
5. Use a representative project-native walking skeleton.
6. Let evidence select the next slice.

Progressive Design is conditional intelligence, not a ceremony required for a
one-line repair.

### 2.3 Durable task history

The work graph supports several goals in one repository or Codex session, a
large goal composed of meaningful child Tasks, repair branches, dependencies,
handoff, pause/resume, and context compaction.

Small implementation steps that share one acceptance target remain checkpoints
inside one Attempt. A child Task exists only when it needs independent state,
evidence, lifecycle, ownership, or stopping conditions.

### 2.4 Adaptive feedback

Every failed or partial Attempt can preserve observation, evaluation, diagnosis,
decision, and next plan. Semantic decisions are Agent judgments and are always
explicit. Code validates the vocabulary and mechanical state; it never infers
repair, redesign, or pivot from keywords.

### 2.5 Verification and authority

Worker self-report is never completion evidence. A locked VerificationSpec runs
against one sealed Attempt. A Review approves one exact Evaluation. Acceptance
resolves one linear chain and cannot approve a different or later workspace.

### 2.6 Recovery and task switching

RecoveryView gives a new session a bounded, source-bound entry point: the Task
and Contract heads, active/latest Attempt, decisions, dependency heads, evidence
refs, acceptance chain, and current workspace alignment.

Recovery is a projection, not a second memory system and not a transcript.

## 3. Non-Goals and Hard Boundaries

The final cut must not add or retain these as active product behavior:

- Mission Capsule, ExecutionReport, or VerificationResult as a second contract,
  execution, or verification model;
- V1/V2 compatibility commands, dual-write artifacts, or migration authority;
- a scheduler, daemon, watcher, autonomous agent pool, or hidden routing loop;
- transcript storage, vector memory, automatic semantic summarization, or a
  project-management UI;
- automatic architecture judgment or keyword-based semantic routing;
- project-specific tasks, metrics, datasets, business rules, or domain policy
  inside MetaLoop core;
- a claim that declared path scope is a sandbox or a non-bypassable permission
  boundary.

The final cut may keep a historical architecture note outside the active Skill,
but active code and Skill instructions must expose only the final model.

## 4. Sources of Truth

### 4.1 Project documents

Project-owned documents contain architecture, module contracts, migration plans,
domain assumptions, and design prose. MetaLoop stores references and hashes when
the Contract needs those facts to remain stable. It never copies architecture
prose into core state.

### 4.2 Git worktree

Every authoritative MetaLoop Project is bound to a local Git repository and
worktree. GitHub, SSH, a remote repository, or a clean worktree are not required.
The Git worktree supplies repository identity, branch/worktree identity, HEAD,
changed paths, and content fingerprints.

Git does not decide whether work is correct and does not replace Task state.

### 4.3 SQLite

SQLite stores protocol identity, immutable records, lifecycle state, CAS versions,
foreign-key references, event cursors, evidence refs, and acceptance heads. It
is the only mutable operational truth.

JSON and Markdown exports under `.metaloop/` are projections and may be deleted
and rebuilt. They are never write authorities.

## 5. Minimal Authoritative Algebra

The final protocol has seven authoritative records, two value objects, and one
derived projection.

| Record | Responsibility |
| --- | --- |
| `Project` | Repository/worktree identity and navigation defaults |
| `Task` | Recoverable, pausable, branchable goal and lifecycle |
| `ContractRevision` | Immutable goal, boundaries, acceptance, and validators |
| `Attempt` | One execution strategy under one exact ContractRevision |
| `Evidence` | Workspace file reference with exact content hash |
| `DecisionEvent` | Append-only observation, diagnosis, decision, or next plan |
| `Evaluation` | Immutable judgment over one exact subject |
| `WorkspaceStamp` | Value object describing one mechanical Git state |
| `RecoveryView` | Derived source-bound resume and alignment projection |

`Review` is an Evaluation whose subject is another Evaluation and whose
authority is explicit. It does not create a second approval model.

### 5.1 Orthogonality rules

- `Project` identifies a workspace; it is not an implicit mutation subject.
- `Task` owns lifecycle, dependencies, and current immutable heads; it does not
  contain mutable execution status inside the Contract.
- `ContractRevision` defines success and boundaries; it cannot be silently
  edited after lock.
- `Attempt` describes what one strategy did; it cannot change its Contract.
- `Evidence` proves file identity; it does not prove semantic success.
- `DecisionEvent` records a judgment; it does not independently mutate Task
  lifecycle.
- `Evaluation` judges one immutable subject; it never approves the current
  workspace generically.
- `WorkspaceStamp` proves mechanical state; it does not infer meaning.
- `RecoveryView` is derived and never a write source.

### 5.2 Required reference chain

```text
Project / Workspace
  -> Task
  -> ContractRevision
  -> Attempt(contract_ref, baseline_stamp)
  -> Evidence(path, sha256)
  -> Evaluation(attempt_ref, attempt_hash)
  -> Review(evaluation_ref, evaluation_hash)
  -> Task.acceptance_head
```

Every immutable reference carries an ID and content hash. Every mutation names
its explicit Task, Attempt, or Evaluation and uses Task `state_version` for
compare-and-swap transitions.

## 6. ContractRevision Shape

ContractRevision is the only task contract. The exact storage format may be
normalized, but the semantic fields are fixed:

```json
{
  "schema": "metaloop.final.contract",
  "version": "1.0",
  "goal": "Observable target outcome.",
  "rationale": ["Why this target and strategy matter."],
  "constraints": ["Resource, permission, compatibility, or risk limits."],
  "non_goals": ["Explicitly excluded outcomes."],
  "acceptance_criteria": ["Observable success statements."],
  "verification_spec": {
    "validators": [],
    "resource_gates": []
  },
  "protocol_shape": "single_node",
  "execution_scope": {
    "paths": ["src", "tests"],
    "stable_inputs": [
      {
        "role": "governing_document",
        "path": "docs/architecture.md",
        "sha256": "sha256:<digest>"
      }
    ],
    "managed_outputs": [
      {
        "role": "implementation",
        "path": "src/feature.py"
      }
    ],
    "change_kind": "extension",
    "migration_plan": null
  }
}
```

`execution_scope` is optional for ordinary work but Git workspace alignment is
always required. `paths` is a declaration for task clarity, not a sandbox.
`stable_inputs` must retain exact hashes. `managed_outputs` must become exact
Attempt Evidence before seal. `change_kind` is explicit and required only when
architecture-sensitive governance is needed. `redesign` requires a locked
`migration_plan`.

The final implementation may keep the scope value object in a separate module,
but it must not expose an independent governance state machine.

## 7. Git Workspace Contract

### 7.1 Project initialization

`project init` must fail if:

- Git is unavailable;
- the workspace is not inside a Git repository;
- the repository root cannot be resolved;
- the worktree identity cannot be read;
- Git status cannot be obtained.

The Project records repository root, worktree path, and adapter version. A
remote repository is irrelevant to runtime correctness.

### 7.2 WorkspaceStamp

`WorkspaceStamp` is a deterministic value object, not a new memory system:

```text
adapter = git
adapter_version
repository_root
worktree_path
head_oid
index_digest
worktree_digest
changed_paths_digest
changed_path_count
unknown_reason = null | <bounded diagnostic>
```

The adapter must:

1. Resolve repository root and worktree path.
2. Read HEAD and index state.
3. Read `git status --porcelain=v2 --untracked-files=all`.
4. Normalize path/status entries in stable order.
5. Hash changed file bytes or Git object identities without storing contents in
   SQLite.
6. Exclude `.git/`, `.metaloop/`, and ignored generated files from the generic
   scan.
7. Recheck `managed_outputs` and Evidence separately, even when a file is
   ignored by Git.
8. Return `unknown`, never a false aligned result, when Git fails or a bounded
   scan limit is exceeded.

The implementation may use Git-native object IDs and diff metadata when they
are content-complete. It must not use only mtime or only the changed path set:
editing the same file twice must change the stamp.

### 7.3 Attempt baseline and checkpoint

At Attempt start, record `baseline_stamp` in the immutable Attempt header and
the first Attempt record. At every semantic checkpoint, record:

```text
workspace_stamp
completed
observations
diagnosis
decision
next_plan
claimed_paths
deferred_paths
evidence_refs
```

The semantic fields are written by the Agent; the workspace stamp is computed
by code at write time.

### 7.4 Alignment states

The live workspace comparison returns exactly one state:

| State | Meaning | Gate behavior |
| --- | --- | --- |
| `aligned` | Current stamp equals the latest checkpoint stamp | Continue |
| `ahead` | Project changed after the latest checkpoint | Require checkpoint/reconcile |
| `conflicted` | Changes cannot be attributed to the current scope or worktree | Require explicit resolution |
| `unknown` | Git or bounded observation failed | Fail closed |

`RecoveryView.fresh` is true only when its SQLite source refs are current and
the workspace state is `aligned`. A database-only fresh projection is not
considered sufficient.

## 8. Lifecycle and Safe Points

### 8.1 Preflight

Before substantial work, the Skill and kernel resolve:

- explicit Project and Task;
- current Task state version;
- ContractRevision head;
- dependency readiness;
- control intent;
- RecoveryView source and workspace alignment;
- duplicate Attempt guard;
- Git worktree identity.

### 8.2 Frame

Codex performs bounded inspection and Progressive Design, then locks one
ContractRevision. The Contract is not a project transcript and does not contain
mutable lifecycle state.

### 8.3 Work

The Agent starts one Attempt for one strategy. Meaningful progress is kept as
append-only Attempt checkpoints. A small implementation slice remains within
the Attempt until its own evidence, lifecycle, or ownership requires a child
Task.

### 8.4 Reconcile

When the workspace is `ahead`, the Agent must classify the delta:

```text
claim    -> belongs to the current Attempt
defer    -> intentionally not part of the current Attempt, with reason
assign   -> belongs to another explicit Task
conflict -> cannot safely attribute; stop and resolve
```

MetaLoop never guesses Task ownership from filenames or prose.

### 8.5 Adapt

After partial or failed verification, append observation, evaluation, diagnosis,
an explicit decision, and a next plan before another Attempt. Exact replay is
blocked unless a concrete `retry_reason` is recorded.

### 8.6 Finish

The only completion path is:

```text
checkpoint aligned
  -> attach exact Evidence
  -> seal Attempt
  -> verify sealed Attempt
  -> satisfy Review/user authorities when required
  -> accept exact Evaluation
```

Every transition uses compare-and-swap and revalidates live Evidence,
ContractRevision content, and WorkspaceStamp alignment.

### 8.7 Handoff and task switching

Before changing Tasks, threads, or sessions, the Agent must checkpoint or
record a DecisionEvent and refresh RecoveryView. A child Task may unblock or
provide evidence to a parent, but never completes the parent implicitly.

One worktree permits one active mutating Attempt at a time. Parallel mutating
work uses separate Git worktrees and separate Project identities. This is a
deliberate clarity rule, not a scheduler.

## 9. Six Gates in the Final Protocol

| Gate | Agent behavior | Code truth |
| --- | --- | --- |
| Design | Understand, question, model, and choose the smallest slice | Lock ContractRevision |
| State | Checkpoint meaningful progress and next plan | Hash Attempt records and stamps |
| Verification | Run tests and interpret results | Evaluate exact sealed Attempt |
| Adaptive | Diagnose before retrying | Validate explicit decision vocabulary |
| Control | Honor explicit halt/resource/revise intent | Read immutable control intent at safe points |
| Observation | Inspect status, blockers, and recovery | Derive read-only summaries and freshness |

The Skill surface stays outcome-first. Users should be able to say only:

```text
Use $metaloop. I want to <goal>.
```

Protocol names are hidden unless the user is diagnosing MetaLoop itself.

## 10. Minimal Active Command Surface

The final Skill exposes only the canonical path:

```text
project init / status / integrity / export
task create / list / show / contract / transition / depend
task decision / assign / return
attempt start / record-checkpoint / evidence / seal / abort / show
evaluate verify / review / accept / show
recover show / write
observe
```

`attempt record-checkpoint` is a semantic convenience over the append-only
Attempt record API. It computes the current WorkspaceStamp automatically.

The final active Skill must not expose V1 `design`, `run`, `verify`, capsule
status files, legacy adaptive files, or a second event/task ontology.

## 11. Module Ownership

The canonical source lives under `src/metaloop_core/`; the installed Skill gets
a generated vendored copy. The portable kernel is only a bootstrap and argument
adapter.

Recommended modules:

```text
workspace.py       Git identity, status, WorkspaceStamp, alignment
schemas.py         final record schemas and enum vocabulary
contracts.py       ContractRevision shape, scope and hash validation
durable.py         SQLite transactions, CAS, lifecycle and reference integrity
recovery.py        RecoveryView source projection and freshness
verification.py    validators, Evaluation, Review and acceptance chain
decisions.py       DecisionEvent and adaptive decision validation
cli.py             canonical command adapter and presentation
```

No module may own a competing Task identity or persist a project-specific
policy. `engineering_governance.py` should be absorbed into Contract scope and
reference validation rather than remain an independent active subsystem.

## 12. Host Integration and Guarantee Boundary

The Skill alone cannot force an Agent that bypasses every protocol command.
The strongest portable guarantee is therefore fail-closed lifecycle behavior:
an unaligned or unknown workspace cannot be accepted.

Where a Codex host exposes hooks, a thin adapter should invoke a read/check at:

- turn start and turn end;
- after a bounded batch of mutating tool calls;
- before context compaction;
- before handoff or Task switch;
- before seal, verify, and accept.

This adapter is synchronous and optional. It is not a daemon, watcher, agent
brain, or scheduler. The core remains correct when only explicit MetaLoop
commands are available, although divergence is discovered at the next protocol
entry rather than continuously in the background.

The guarantee is precise:

```text
No unacknowledged WorkspaceStamp may pass acceptance.
```

Any lifecycle operation that cannot prove this property must fail closed: it
returns an actionable state and leaves the Task incomplete rather than guessing
that the workspace is aligned.

The protocol does not promise that every uncommitted thought or every semantic
Agent intention is automatically recovered. It does promise that mechanical
project changes are surfaced and that completion cannot silently ignore them.

## 13. Clean-Cut Removal Plan

Because there are no formal external users, the final implementation is a
breaking clean cut:

1. Replace the schema namespace with the final contract and record schemas.
2. Remove V1 capsule, execution, verification, context, and adaptive write
   paths from the installed Skill.
3. Remove `project migrate-legacy` and `legacy_unbound` acceptance behavior.
4. Remove duplicate routing, tick, relay, and activation entry points from the
   active command surface. Preserve only future-facing notes outside the Skill.
5. Remove compatibility projections from canonical lifecycle code.
6. Rebuild the Skill package from the one canonical core.
7. Reinitialize local development `.metaloop/` state under the final schema.

Historical documents may remain in Git as design records, but they must not be
loaded as active protocol instructions.

## 14. Implementation Phases

### Phase 0: Contract and boundary freeze

- Add this document as the implementation contract.
- Freeze the final record names and authority rules.
- List all V1/V2 modules and commands to delete.
- Add a final schema namespace and reject old active payloads.

### Phase 1: Git workspace adapter

- Implement repository/worktree identity checks.
- Implement deterministic WorkspaceStamp.
- Test staged, unstaged, untracked, deleted, renamed, branch, reset, and
  unknown/error states.
- Keep `.metaloop/` out of generic workspace observation.

### Phase 2: Contract and Attempt integration

- Add baseline stamp to Attempt start.
- Add stamp binding to checkpoint records.
- Normalize execution scope and stable/managed refs into ContractRevision.
- Require managed output Evidence before seal.

### Phase 3: Recovery and lifecycle gates

- Make RecoveryView freshness include workspace alignment.
- Add `ahead`, `conflicted`, and `unknown` diagnostics.
- Block seal, verify, review, accept, and handoff when alignment is unsafe.
- Revalidate Git identity and Evidence after external validators run.

### Phase 4: Skill and host discipline

- Rewrite the Skill around Frame, Work, Reconcile, Adapt, Prove.
- Add the checkpoint safe-point instructions and minimal command examples.
- Add the optional host hook adapter without adding a daemon.
- Ensure user-facing text hides protocol mechanics by default.

### Phase 5: Remove the old surface

- Delete legacy modules, commands, schemas, and active references.
- Delete duplicate semantic classifiers and compatibility branches.
- Regenerate the vendored Skill core.
- Reinitialize development state under the final schema.

### Phase 6: Dogfood and release

- Run the MetaLoop protocol on its own final upgrade task.
- Run a long architecture task with at least one repair child and one paused
  Task switch.
- Run a context-compaction recovery test.
- Run a workspace-drift and external-edit test.
- Install the complete Skill into a clean target and run the same smoke suite.

## 15. Required Test Matrix

### Workspace and Git

- Project initialization outside Git fails.
- Repository root and worktree identity are stable.
- Clean, staged, unstaged, untracked, deleted, renamed, and binary changes
  produce distinct stamps.
- Editing the same path twice changes the stamp.
- Branch switch, reset, unavailable Git, and bounded-scan overflow produce
  `unknown` or `conflicted`, never false `aligned`.
- `.metaloop/` changes do not create workspace drift.
- Ignored managed outputs are still checked through explicit Evidence.

### Lifecycle and recovery

- Attempt baseline is immutable.
- A file change without checkpoint marks Recovery `ahead`.
- A checkpoint at the current stamp returns Recovery to `aligned`.
- A change after checkpoint blocks seal.
- A change after seal blocks verify/review/accept or integrity as appropriate.
- A crashed/open Attempt is recoverable from stamp, records, and bounded events.
- Context compaction and Task switch preserve the next plan and changed paths.

### Task graph and semantics

- Small steps stay within one Attempt.
- Repair child records parent and origin event but cannot complete the parent.
- Dependencies block Attempt start and unblock only through accepted child state.
- One worktree has one active mutating Attempt.
- Multiple worktrees have distinct Project identities.
- Explicit repair/redesign/pivot values are accepted; prose keywords never route.
- Exact replay requires a concrete retry reason.

### Contract, evidence, and authority

- ContractRevision is immutable after lock.
- Stable input drift blocks all relevant lifecycle gates.
- Managed outputs require exact Attempt Evidence before seal.
- Evaluation binds one sealed Attempt hash.
- Review binds one Evaluation hash and rejects worker self-review.
- Acceptance requires one valid linear authority chain.
- A changed file cannot be authorized by an old Evaluation.

### Distribution

- Canonical and vendored core are byte-identical.
- The portable kernel needs only Python `3.12+` standard library and SQLite.
- The installed Skill has no active V1/V2 compatibility path.
- Clean-target Git initialization, Task execution, recovery, drift blocking, and
  acceptance smoke tests pass.

## 16. Acceptance and Release Criteria

The final architecture is ready for trial only when all statements are true:

- A user can provide only a goal and receive a proportionate Design Gate.
- A one-line repair does not trigger unnecessary Progressive Design ceremony.
- A long architecture task records durable invariants and a smallest slice.
- A new session can recover multiple paused Tasks without chat history.
- A repair branch can contribute evidence without completing its parent.
- No accepted Task has an unacknowledged Git workspace change.
- No Evaluation or Review can authorize a different Attempt.
- No semantic decision is inferred from diagnosis prose.
- All authoritative state is in SQLite, Git, or project-owned documents with a
  clearly declared role.
- No hidden runtime, daemon, vector memory, transcript store, or second Task
  ontology exists.
- Full tests, import boundaries, source/vendor sync, installed Skill parity,
  and `git diff --check` pass.

## 17. Operational Tradeoffs

### Why require Git

Git supplies the lowest-complexity reliable workspace identity and change
fingerprint. It is a local dependency, not a remote service dependency. The
tradeoff is that MetaLoop is intentionally an engineering/artifact workspace
protocol rather than a generic no-files task runner.

### Why not a daemon

A daemon adds deployment, liveness, permission, and race complexity but still
cannot interpret semantic progress. Lazy checks at protocol entries plus
optional host hooks provide the useful guarantee without a hidden runtime.

### Why not record every thought

The objective is durable, verifiable state, not a second transcript. Agents
record compact checkpoints and DecisionEvents; Git and Evidence retain
mechanical identity where needed.

### Why keep semantic decisions in the Skill

Repair, redesign, pivot, and next-plan choices require project understanding.
Keeping them as explicit Agent judgments preserves intelligence while code
enforces vocabulary, references, and lifecycle safety.

## 18. Final Design Invariants

The implementation must preserve these statements as executable tests and
documentation invariants:

```text
Project documents are architecture-content truth.
Git is workspace-change truth.
SQLite is protocol-state truth.
ContractRevision is task-boundary truth.
Agent is semantic-judgment truth.
Attempt is execution truth.
Evaluation is completion truth.
RecoveryView is a derived recovery entry, never a new fact source.
```

The final MetaLoop is therefore a small control layer that lets a capable Agent
work for a long time with good design and engineering discipline, while keeping
the parts that require machine certainty outside the Agent's mutable context.
