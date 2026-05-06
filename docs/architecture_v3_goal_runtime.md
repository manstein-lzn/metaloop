# MetaLoop v3: Mission Governance over Codex Goal Runtime

Last updated: 2026-05-03

## Core Decision

Constitutional architecture reference: `docs/mission_capsule_constitution.md`.

MVP implementation authority: `docs/minimal_v3_codex_goal_architecture.md`.

The current implementation should stay minimal:

```text
MissionSpec -> GoalContract -> Codex goal runtime -> ExecutionReport -> VerificationResult
```

The broader Agent Message Protocol, Structured Context Protocol, Structured Knowledge System, and Intent Transmission Contract are retained as design principles/backlog. They are not immediate v3 MVP implementation scope.

MetaLoop should not default to reimplementing a long-running agent runtime.

Codex `/goal` is now the preferred execution runtime for long tasks. MetaLoop should move up one layer:

```text
MetaLoop = Co-Design + MissionSpec + Mission Compiler + Verification + Audit
Codex /goal = Long-running execution runtime
```

The first real mission showed that MetaLoop's original multi-agent execution loop can complete work, but it is too expensive as the default path. A 12-step plan produced 26 Codex turns, 444 tool calls, about 5.9M tokens, and roughly 70 minutes of runtime for a task that a single Codex agent could plausibly complete much faster.

The lesson is not that the MetaLoop idea is wrong. The lesson is that the default execution engine should be Codex's native goal runtime, while MetaLoop owns task definition and acceptance.

This architecture also adopts a structured context rule:

```text
LLM calls are stateless.
Conversation history is not operational state.
Each LLM call receives a compiled minimal context packet.
```

The detailed structured-context and knowledge-system documents remain useful, but v3 MVP should only implement the smallest subset needed to compile a GoalContract and verify the result.

## Boundary

### Codex `/goal` Owns

- Long-running continuation.
- Pause / resume / clear semantics.
- Runtime goal state.
- Runtime budget state.
- Local code editing and command execution.
- Natural-language objective execution.

`/goal` completion means:

```text
Codex believes the objective is complete.
```

It does not mean:

```text
The MissionSpec has passed structured acceptance.
```

### MetaLoop Owns

- Deep Co-Design.
- MissionSpec generation and locking.
- Scope, constraints, deliverables, risks, and out-of-scope boundaries.
- Mission-to-goal compilation.
- Hard validators.
- Soft review.
- Evidence requirements.
- Final acceptance classification.
- Run audit and state continuity.

MetaLoop completion means:

```text
Codex goal execution completed, then MetaLoop acceptance classified the result.
```

## MissionSpec to Goal Mapping

MetaLoop compiles each MissionSpec into two artifacts.

### 1. Goal Objective

The goal objective is natural language, but it should be structured and explicit.

It includes:

- Intent.
- Deliverables.
- Constraints.
- Out-of-scope items.
- Definition of done.
- Required validation commands to run before Codex marks the goal complete.
- Instructions to record limitations instead of weakening acceptance.

Example:

```text
Objective:
Build a VS Code extension MVP that opens trusted TorchScript traced .pt files,
parses them into a versioned JSON graph, and renders a top-down DAG.

Deliverables:
- package.json with a read-only custom editor for *.pt
- TypeScript extension host
- Python TorchScript parser
- Webview DAG renderer
- README

Constraints:
- local only
- do not upload model files
- require Workspace Trust before parsing
- load TorchScript with map_location="cpu"
- return structured parser errors

Definition of done:
- npm run compile passes
- parser produces versioned JSON for valid traced TorchScript files
- missing Python, missing PyTorch, invalid file, timeout, file-size, and graph-size errors are structured
- README documents usage, configuration, limitations, and security assumptions

Before marking the goal complete:
Run the listed validation commands. Fix failures. If an environment prevents validation,
record exact evidence and limitations.
```

The goal objective may include a structured `GoalContract` JSON block. This is useful, but it remains a strong instruction to Codex rather than a hard runtime guarantee. The protocol is defined in `docs/agent_message_protocol.md`.

### 2. Verification Plan

The verification plan remains inside MetaLoop and is executed after Codex goal completion.

It includes:

- Command validators.
- File existence checks.
- File content checks.
- JSON/schema checks.
- Optional LLM review prompts.
- Evidence requirements.
- Final human acceptance markers when needed.

Example:

```json
{
  "validators": [
    {
      "type": "command",
      "cwd": "torchscript-dag-viewer",
      "cmd": "npm run compile"
    },
    {
      "type": "file_exists",
      "path": "torchscript-dag-viewer/src/extension.ts"
    },
    {
      "type": "file_contains",
      "path": "torchscript-dag-viewer/package.json",
      "text": "customEditors"
    }
  ]
}
```

MetaLoop should also request a Codex-written `ExecutionReport`, for example `.metaloop/execution_report.json`. That report is candidate evidence. MetaLoop must validate its schema and cross-check it against actual validators and artifacts before using it for final acceptance.

## Acceptance Model

MetaLoop must not assume all acceptance can be code validated. Acceptance is layered.

### Hard Validation

Machine-checkable criteria:

- Build passes.
- Tests pass.
- File exists.
- File contains required text.
- JSON/schema is valid.
- CLI command exits with expected code and output.

Required hard validator failures block verified completion.

### Soft Review

LLM-reviewable criteria:

- Architecture quality.
- Product fit.
- Usability.
- Documentation usefulness.
- Security reasoning.
- Whether implementation drifted from MissionSpec.

Soft review must be structured and evidence-based. It should produce findings with severity, evidence, and recommendations.

### Evidence-Based Acceptance

When direct automation is not practical, MetaLoop requests or collects evidence:

- Screenshots.
- Logs.
- Diff summaries.
- Manual reproduction steps.
- Known limitations.
- Build/test transcripts.

Evidence does not equal proof, but it prevents blind acceptance.

### Human Acceptance

Some criteria require user judgment:

- UI taste.
- Product direction.
- Business relevance.
- Final scope satisfaction.

Human acceptance should be explicit and limited to true human judgment points, not used as a fallback for avoidable automation.

Human acceptance is after internal work is finished. It is not a route that the runtime reviewer should choose while agents are still working. The internal reviewer/scheduler routes are implementation routes, such as complete, repair with worker, rethink architecture, replan, brainstorm alternatives, or fail.

## Final Statuses

MetaLoop should replace a single `completed` status with classified completion:

```text
completed_verified
completed_with_soft_acceptance
completed_with_limitations
completed_pending_human_acceptance
blocked
failed
```

This prevents a run from claiming full completion when important validation was skipped or impossible in the current environment.

## Execution Flow

```text
metaloop design
  -> MissionSpec

metaloop compile
  -> goal_objective
  -> GoalContract
  -> IntentTransmissionContract
  -> verification_plan
  -> Structured Context Packet
  -> Knowledge refs

metaloop run
  -> submit goal_objective to Codex /goal
  -> request ExecutionReport
  -> wait/resume/observe goal runtime
  -> collect execution evidence

metaloop verify
  -> validate ExecutionReport
  -> run hard validators
  -> run soft reviewers if configured
  -> check evidence requirements
  -> classify final acceptance

if failed:
  -> generate repair goal
```

## Execution Modes

Default mode should be efficient.

```text
balanced:
  one Codex goal + MetaLoop verification

fast:
  one Codex goal + minimal hard validators

rigorous:
  optional multi-agent planning/review, heavy LLM review, expanded evidence
```

The original `brainstormer -> planner -> worker -> reviewer -> scheduler` execution loop should move to `rigorous` mode. It should not be the default path for ordinary implementation tasks.

## Non-Goals

- Do not make Codex `/goal complete` equal MetaLoop mission completion.
- Do not default to per-step Codex worker plus per-step Codex reviewer.
- Do not let LLM review replace available deterministic validators.
- Do not hide unverifiable criteria under a generic `manual` acceptance result.
- Do not treat a valid-looking Codex `ExecutionReport` as trusted without MetaLoop verification.
- Do not reintroduce recursive MetaLoop spawning into the Kernel.

## Product Thesis

MetaLoop's value is not that it writes code better than Codex.

MetaLoop's value is that it defines the task better, constrains it better, verifies it better, and records the result better.
