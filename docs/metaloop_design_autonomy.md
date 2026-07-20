# MetaLoop Design Autonomy

Date: 2026-07-12

V2 design first resolves an explicit Task, then locks an immutable
ContractRevision. Several independent goals in one workspace receive separate
Task identities. Small actions remain checkpoints inside one Attempt and do
not become Tasks automatically.

MetaLoop exists to reduce user burden, not to make users speak protocol
language. When a user invokes `$metaloop`, Codex should infer and propose the
MetaLoop shape from the project and the goal.

The user supplies:

- intent
- priorities
- constraints
- acceptance judgment
- access decisions for expensive, risky, or external resources

Codex supplies:

- project inspection
- task-shape classification
- Mission Capsule draft
- ExtensionSpec / VerificationSpec draft
- protocol artifact layout
- decision on single-node, multi-thread, or routable work units
- repair, redesign, or handoff discipline after verification

## Entry Behavior

The first `$metaloop` response for a non-trivial task should not jump into
implementation. It should:

- inspect existing `.metaloop/` state
- inspect the relevant project files before proposing a contract
- restate the inferred goal, non-goals, constraints, risks, and unknowns
- classify the task shape
- choose the smallest adequate MetaLoop protocol shape
- propose verification gates and evidence artifacts
- ask only blocking questions
- state safe assumptions when proceeding without user input

Do not ask the user whether to use "Mission Capsule", "VerificationSpec",
"blackboard", "job envelope", "tick", or "relay". Those are MetaLoop internal
mechanisms. Explain the plan in ordinary project terms.

## Progressive Design

For architecture and long-horizon work, design depth and implementation breadth
are independent. Codex may develop a coherent long-term model while locking only
the smallest end-to-end slice that can test its current assumptions.

Codex should:

- expand the user's vision into a target model and identify missing dimensions,
  risks, and choices;
- separate durable invariants from current implementation scope;
- assign cohesive module ownership and explicit interfaces so later slices can
  grow independently;
- record deliberate concessions together with their scope and revisit evidence;
- prefer an established project-native path for the first representative
  walking skeleton;
- use verification evidence from each slice to choose the next increment.

The concrete architecture, modules, slices, concessions, and evidence belong to
the current project. MetaLoop supplies the reasoning discipline; Codex adapts it
to the project's actual constraints and writes the result into project-owned
documents and verification artifacts.

Design dialogue should remain generative. Each response contributes a new
deduction, missing dimension, risk, choice, or clearer structure. Established
context is summarized when doing so produces a more useful shared model.

## Task Shape Classifier

Use the smallest shape that preserves correctness and recovery:

- `single_node`: one local Mission Capsule, one ExecutionReport, one
  VerificationResult, and one Adaptive Goal Loop are enough.
- `multi_thread`: several persistent Codex threads are useful, but they share
  one workspace truth through `.metaloop/` artifacts.
- `routable_work_units`: separate workspaces or responsibility boundaries need
  job envelopes, outbox records, relay delivery, and shared blackboard facts.

Escalate from `single_node` only when the task needs real isolation:

- independent design / implementation / review responsibilities
- long-running attempts with hard gates
- cross-workspace handoff
- different resource profiles
- strong context isolation
- downstream work that must not see upstream debugging noise

## Blocking Questions

Ask only when the answer changes the contract or risk profile.

Blocking questions include:

- final acceptance target is ambiguous
- user approval is required for cost, time, credentials, network, data access,
  or destructive changes
- project authority is unclear
- the task goal conflicts with existing constraints
- verification would otherwise be fake or too weak

Non-blocking details should become assumptions in the draft capsule, with the
assumption made explicit and revisable before locking.

## Target-Project Artifacts

Codex may create or revise these artifacts in the user's target project when
the task shape requires them:

- `.metaloop/mission_capsule.json`
- `.metaloop/execution_report.json`
- `.metaloop/verification_result.json`
- `.metaloop/adaptive_loop.json`
- `.metaloop/event_log.jsonl`
- `.metaloop/threads.json`
- `global_blackboard.json`
- `dispatch_map.json`
- `job_envelope.json`
- envelope templates for downstream roles

These artifacts belong to the target project. MetaLoop core and skill docs must
remain domain-neutral and must not contain project-specific tasks, datasets,
metrics, or business rules.

## Verification Discipline

Design autonomy does not mean trusting the agent's own claims.

Before execution, Codex should draft gates that distinguish:

- hard completion gates
- advisory review criteria
- evidence artifacts
- reproducibility requirements
- resource or authority blockers
- forbidden claims
- manual acceptance requirements

For metric, quality, benchmark, or long-horizon goals, file existence alone is
not enough. The draft must include a meaningful executable gate, a manual
blocking review, or a clear reason why only partial verification is possible.

## Acceptance

This protocol is working when a user can say only:

```text
Use $metaloop. I want to <goal>.
```

and Codex still performs project inspection, proposes the contract, chooses the
protocol shape, asks only necessary questions, locks verification before
execution, and records feedback after every attempt.
