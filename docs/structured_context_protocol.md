# Structured Context Protocol

Last updated: 2026-05-02

## Core Thesis

LLM calls are stateless function invocations.

The model receives a sequence of tokens and returns a sequence of tokens. A chat application's "conversation context" is not a special primitive. It is a client-side strategy that replays or summarizes prior messages into the next input.

That strategy is convenient for human conversation, but it is often inefficient for autonomous software work.

MetaLoop should treat each LLM invocation as an independent call with a compiled context packet:

```text
System State
  -> ContextCompiler
  -> Structured Context Packet
  -> LLM Runtime
  -> Structured Result
  -> Verification / State Update
```

The durable state is not the chat history.

The durable state is:

- MissionSpec.
- EventStore.
- ArtifactStore.
- WorkspaceState.
- VerificationState.
- DecisionRecords.
- PolicyState.
- BudgetState.

Conversation history can be an artifact, but it should not be the primary operational memory.

## Problem

Most agent systems pass long natural-language context to the model:

```text
Here is the prior conversation...
Here is what we discussed...
Here is what happened...
Here is the code...
Please continue...
```

This causes four problems.

### 1. Token Waste

The same mission, constraints, logs, and prior decisions are repeatedly transmitted.

Even if the provider caches some input, the system still pays in latency, complexity, and model attention.

### 2. Low Information Density

Natural language is verbose and mixed-purpose. It blends facts, guesses, rationale, stale context, user preference, and current task instruction in one stream.

The model has to infer which parts are authoritative.

### 3. Weak Routing Semantics

When state is expressed as prose, downstream routing becomes fragile.

Bad pattern:

```text
The reviewer seemed mostly okay, so maybe continue.
```

Good pattern:

```json
{
  "review_decision": "pass",
  "blocking_findings": 0,
  "allowed_routes": ["next_step", "complete"]
}
```

### 4. Poor Reproducibility

If a call depends on a large rolling chat transcript, it is hard to reproduce why the model made a decision.

If a call depends on a versioned context packet with artifact refs, the input can be stored, replayed, diffed, and audited.

## Design Principle

MetaLoop should not ask:

```text
What conversation should we continue?
```

It should ask:

```text
What is the minimal sufficient context for this role, this objective, this moment?
```

Each LLM call should receive:

- Current objective.
- Mission digest.
- Relevant constraints.
- Relevant state.
- Evidence refs.
- Allowed scope.
- Acceptance checks.
- Output contract.

It should not receive:

- Full chat history by default.
- Full event log by default.
- Full command logs inline.
- Full repository dump.
- All prior reasoning.
- Stale alternatives that are no longer active.

## Guided Autonomy

Structured context is not static RAG.

MetaLoop should not try to precompute every relevant chunk and prevent the agent from exploring. Coding agents are capable investigators. They should receive intent, boundaries, refs, tools, and acceptance criteria, then actively inspect the workspace inside their authority.

Context packets should include an `exploration_policy` when the role is expected to investigate.

Example:

```json
{
  "exploration_policy": {
    "mode": "guided_autonomy",
    "allowed_tools": ["rg", "sed", "git diff", "pytest"],
    "allowed_paths": ["src/metaloop", "tests"],
    "forbidden_paths": [".env", ".metaloop/private"],
    "recommended_entrypoints": [
      "sks://doc/structured_knowledge_system#reference-scheme"
    ],
    "search_strategy": [
      "Prefer rg for symbols and tests before broad file reads.",
      "Read only files relevant to the current objective.",
      "Run focused validation after edits."
    ]
  }
}
```

Refs are navigational entrypoints, not a complete replacement for tool-driven exploration.

See `docs/guided_autonomy_principle.md`.

## Structured Context Packet

A context packet is a compact, typed input to an LLM call.

Example:

```json
{
  "schema": "metaloop.context_packet",
  "version": "1.0",
  "packet_id": "ctx_001",
  "run_id": "run_123",
  "mission_id": "mission_abc",
  "role": "worker",
  "objective": {
    "type": "repair",
    "summary": "Fix TypeScript compile failure",
    "target_check_id": "npm_compile"
  },
  "mission_digest": {
    "intent": "Build a VS Code extension MVP for viewing TorchScript DAGs.",
    "deliverables": [
      "TypeScript extension host",
      "Python parser",
      "Webview DAG renderer",
      "README"
    ],
    "non_negotiable_constraints": [
      "Do not upload model files",
      "Require Workspace Trust before parsing",
      "Do not weaken acceptance criteria"
    ],
    "out_of_scope": [
      "Marketplace publishing",
      "Untrusted .pt sandboxing"
    ]
  },
  "current_state": {
    "failed_check": {
      "check_id": "npm_compile",
      "cmd": "npm run compile",
      "cwd": "torchscript-dag-viewer",
      "exit_code": 2,
      "log_ref": "artifact://run_123/logs/npm_compile.txt"
    },
    "changed_files": [
      "torchscript-dag-viewer/src/parserService.ts"
    ]
  },
  "scope": {
    "allowed_paths": [
      "torchscript-dag-viewer/src",
      "torchscript-dag-viewer/package.json"
    ],
    "forbidden_paths": [
      "metaloop.mission.json"
    ],
    "forbidden_actions": [
      "remove_tests_to_pass",
      "weaken_acceptance",
      "delete_required_feature"
    ]
  },
  "evidence": [
    {
      "type": "artifact_ref",
      "uri": "artifact://run_123/logs/npm_compile.txt",
      "description": "Current compile failure log"
    }
  ],
  "acceptance": {
    "required_checks": [
      {
        "check_id": "npm_compile",
        "type": "command",
        "cmd": "npm run compile",
        "cwd": "torchscript-dag-viewer"
      }
    ]
  },
  "output_contract": {
    "schema": "metaloop.execution_report",
    "required_path": ".metaloop/execution_report.json"
  }
}
```

The packet is not just JSON formatting. It is semantic compression.

Bad packet:

```json
{
  "description": "A long natural-language recap of everything that happened..."
}
```

Good packet:

```json
{
  "failed_check": "npm_compile",
  "exit_code": 2,
  "log_ref": "artifact://run_123/logs/npm_compile.txt",
  "allowed_paths": ["torchscript-dag-viewer/src"],
  "forbidden_actions": ["weaken_acceptance"]
}
```

## Context Compiler

The ContextCompiler transforms durable state into a minimal sufficient context packet.

Inputs:

- MissionSpec.
- Current run state.
- EventStore.
- ArtifactStore.
- WorkspaceState.
- VerificationState.
- PolicyState.
- BudgetState.
- Role.
- Current objective.

Output:

- Structured Context Packet.

The compiler has two responsibilities.

### 1. Selection

Choose what the model needs for this call.

Examples:

- Worker needs current objective, allowed files, relevant failure logs, acceptance checks.
- Reviewer needs mission digest, diff summary, changed files, evidence, acceptance criteria.
- Scheduler needs validator results, review decisions, budget state, allowed routes.
- Goal runtime needs goal objective, GoalContract, required report path.

### 2. Compression

Convert raw state into dense facts and refs.

Examples:

- Long logs become `ArtifactRef`.
- Full mission becomes `MissionDigest`.
- Full diff becomes `DiffSummary` plus optional patch ref.
- Long Co-Design history becomes `DecisionRecords`.
- Repeated failures become `FailureSummary`.

## Code Compiler vs LLM Distiller

MetaLoop should use two compilation paths.

### Deterministic Context Compiler

Used by default.

Suitable for:

- Mission fields.
- Validator results.
- Event latest state.
- Changed files.
- Artifact refs.
- Policy constraints.
- Budget state.
- Allowed routes.

This path should be code-driven and testable.

### LLM Context Distiller

Used only when deterministic compression is insufficient.

Suitable for:

- Condensing long design discussions into decision records.
- Summarizing large diffs into semantic changes.
- Summarizing repeated failure attempts into hypotheses.
- Producing module maps for large codebases.

The distiller output must itself be structured and validated. It should never become an untrusted blob of prose that drives scheduler-critical decisions.

## Role-Specific Packets

### GoalContextPacket

For Codex `/goal`.

Contains:

- Natural-language objective.
- GoalContract.
- Definition of done.
- Required report path.
- Validation commands to attempt.
- Rules about limitations and evidence.

### WorkerContextPacket

For implementation or repair work.

Contains:

- Current objective.
- Mission digest.
- Allowed scope.
- Relevant files or file summaries.
- Failure evidence.
- Acceptance checks.
- Output contract.

### ReviewerContextPacket

For review.

Contains:

- Mission digest.
- Change summary.
- Changed files.
- Diff refs.
- Evidence refs.
- Acceptance criteria.
- Review rubric.
- Required decision schema.

### SchedulerContextPacket

For route decision logic or optional LLM-assisted routing.

Contains:

- Validator results.
- Review decisions.
- Budget state.
- Retry counts.
- Allowed routes.
- Blocking conditions.

Scheduler-critical final routing must remain MetaLoop-controlled.

## Relationship to SKS and AMP

Structured Knowledge System, Intent Transmission Contract, Structured Context Protocol, and Agent Message Protocol are related but distinct.

```text
SKS: where project knowledge lives and how refs are indexed, permissioned, and resolved.
ITC: what intent, authority, situation, acceptance, and feedback must be transmitted.
SCP: how MetaLoop compiles role-specific LLM inputs from refs and durable state.
AMP: how MetaLoop components exchange structured messages.
```

SCP should become reference-first when SKS is available.

```text
Docs / Code / Mission / Events / Artifacts / Decisions
  -> SKS
  -> permissioned refs
  -> IntentTransmissionContract
  -> ContextCompiler
  -> reference-first ContextPacket
```

The detailed SKS design is in `docs/structured_knowledge_system.md`.
The detailed ITC design is in `docs/intent_transmission_contract.md`.

## Relationship to AMP

```text
AMP: how MetaLoop components exchange structured messages.
SCP: how MetaLoop compiles state into LLM inputs.
```

Flow:

```text
MissionSpec + EventStore + Artifacts + WorkspaceState
  -> ContextCompiler
  -> ContextPacket
  -> LLM adapter
  -> ExecutionReport / ReviewResult / RouteRecommendation
  -> AMP message
  -> MetaLoop validation and state update
```

## Relationship to Codex `/goal`

Codex `/goal` still receives tokens. It does not bypass the language model input/output mechanism.

MetaLoop can improve goal efficiency by sending:

- Concise objective.
- Structured GoalContract.
- Artifact refs.
- Required report path.
- Minimal relevant constraints.

But Codex `/goal` does not enforce the schema. It follows the contract as model instruction.

Therefore:

```text
Structured context improves density and precision.
It does not replace MetaLoop verification.
```

## Expected Benefits

### Token Efficiency

The model sees only relevant state instead of a full transcript.

### Time Efficiency

Smaller, clearer inputs reduce model latency and reduce unnecessary tool calls.

### Higher Precision

The model receives typed facts and constraints instead of ambiguous prose.

### Better Auditability

Each context packet can be stored, hashed, replayed, and diffed.

### Better Role Isolation

Each role receives the information it needs, not the entire global context.

### Better Recovery

If a run is interrupted, MetaLoop can regenerate the next context packet from durable state rather than relying on an opaque chat history.

## Limits

Structured context is not automatically shorter than natural language.

JSON has overhead. Badly designed packets can be longer and worse than prose.

The gain comes from:

- Omitting irrelevant context.
- Replacing large raw text with refs.
- Replacing verbose explanation with typed facts.
- Avoiding repeated history replay.
- Making output contracts explicit.

## Anti-Patterns

- Dumping full chat history into a JSON string.
- Dumping full logs inline.
- Passing every field to every role.
- Treating LLM-produced summaries as trusted facts.
- Letting free-form rationale drive scheduler-critical decisions.
- Recomputing context by asking the LLM to "remember" prior turns.
- Using structure for appearance while keeping all semantics in prose.

## Implementation Plan

Add:

```text
src/metaloop/context.py
```

Initial schemas:

- `ContextPacket`
- `MissionDigest`
- `WorkspaceDigest`
- `GoalContextPacket`
- `WorkerContextPacket`
- `ReviewerContextPacket`
- `SchedulerContextPacket`
- `ContextCompiler`
- `ContextArtifactRef`
- `KnowledgeRef`
- `ExplorationPolicy`

Initial compiler inputs:

- `MissionSpec`
- latest `KernelState`
- recent `SystemEvent`s
- validator results
- changed files
- artifact refs
- knowledge refs
- exploration policy
- role
- current objective

Initial tests:

- Worker packet excludes full event log.
- Reviewer packet includes changed files and evidence refs.
- Scheduler packet includes allowed routes and validator results.
- Full logs become artifact refs.
- Indexed docs/code/events become knowledge refs.
- Packet contains schema/version.
- Invalid packet is rejected.
- Exploration policy is present for worker/repair packets.

## Architectural Rule

MetaLoop state is durable.

LLM context is compiled.

Chat history is optional evidence, not operational memory.

If content is indexed in SKS, ContextCompiler should pass a ref by default and resolve only the minimum permitted summary or excerpt needed for the role.
