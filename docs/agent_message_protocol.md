# MetaLoop Agent Message Protocol

Last updated: 2026-05-02

## Purpose

MetaLoop needs structured communication between Co-Design, mission compilation, execution adapters, validators, reviewers, scheduler logic, and future agents.

The protocol goal is:

```text
machine-readable first, natural-language explanatory second
```

Natural language remains allowed in fields such as `summary`, `rationale`, `notes`, and `open_questions`. It must not be the only source of truth for routing, acceptance, or audit.

## Scope

This protocol is local-first and MetaLoop-specific.

It covers:

- Work orders.
- Goal contracts.
- Execution reports.
- Evidence packets.
- Validation results.
- Review results.
- Route decisions.
- Repair requests.

It does not replace:

- User-facing Co-Design conversation.
- Codex `/goal` runtime state.
- Low-level OpenTelemetry traces.

## Protocol Layers

MetaLoop uses three structured layers.

### 1. Mission Contract

Produced by Co-Design and locked before execution.

Examples:

- `MissionSpec`
- `AcceptanceCriteria`
- `RiskPolicy`
- `VerificationPlan`

### 2. Agent Message Protocol

Used by MetaLoop components and future agents.

Examples:

- `AgentMessage`
- `WorkOrder`
- `WorkResult`
- `ReviewCompleted`
- `RouteDecision`
- `RepairRequest`
- `EvidencePacket`

### 3. Event Protocol

Used for audit, replay, and monitoring.

Examples:

- `RunStarted`
- `GoalSubmitted`
- `ValidatorCompleted`
- `ReviewCompleted`
- `MissionClassified`

## Envelope

All AMP messages use a shared envelope:

```json
{
  "schema": "metaloop.agent_message",
  "version": "1.0",
  "message_id": "msg_123",
  "run_id": "run_123",
  "mission_id": "mission_abc",
  "sender": {
    "role": "planner",
    "id": "planner_1"
  },
  "recipient": {
    "role": "worker",
    "id": "worker_1"
  },
  "message_type": "work_order.created",
  "payload": {},
  "evidence": [],
  "confidence": "medium",
  "requires_response": true,
  "created_at": "2026-05-02T10:00:00Z"
}
```

Rules:

- `schema` and `version` are required.
- `message_type` selects the payload schema.
- `payload` must validate against the selected schema.
- `evidence` contains references, not large inline logs.
- Invalid scheduler-critical messages must be rejected, not guessed.

## Artifact References

Large content must be stored as artifacts and referenced.

```json
{
  "type": "artifact_ref",
  "uri": "artifact://run_123/logs/npm-test.txt",
  "sha256": "abc123",
  "media_type": "text/plain",
  "description": "npm test output"
}
```

Use artifact refs for:

- Logs.
- Diffs.
- Screenshots.
- Long command output.
- Generated reports.
- Large code excerpts.

## Evidence

Claims should be evidence-backed.

```json
{
  "claim": "npm run compile passed",
  "evidence": [
    {
      "type": "command_result",
      "cmd": "npm run compile",
      "cwd": "torchscript-dag-viewer",
      "exit_code": 0,
      "output_ref": "artifact://run_123/logs/npm-compile.txt"
    }
  ]
}
```

Evidence is not always proof, but it makes acceptance auditable.

## Core Payloads

### WorkOrder

Planner or scheduler to worker.

```json
{
  "message_type": "work_order.created",
  "payload": {
    "work_order_id": "wo_001",
    "objective": "Implement parser timeout handling",
    "scope": {
      "allowed_paths": [
        "src/parserService.ts",
        "tests/test_parser_service.ts"
      ],
      "forbidden_paths": [
        "metaloop.mission.json"
      ]
    },
    "expected_artifacts": [
      "timeout error mapped to structured parser error",
      "test covering timeout path"
    ],
    "acceptance_checks": [
      {
        "type": "command",
        "cmd": "npm test",
        "cwd": "torchscript-dag-viewer"
      }
    ],
    "constraints": [
      "Do not change public setting names",
      "Keep error code stable"
    ]
  }
}
```

### WorkResult

Worker to reviewer or scheduler.

```json
{
  "message_type": "work_order.completed",
  "payload": {
    "work_order_id": "wo_001",
    "status": "implemented",
    "changed_files": [
      "src/parserService.ts",
      "tests/test_parser_service.ts"
    ],
    "summary": "Added timeout mapping and tests.",
    "validation_results": [
      {
        "check_id": "npm-test",
        "status": "passed",
        "output_ref": "artifact://run_123/logs/npm-test.txt"
      }
    ],
    "known_limitations": []
  }
}
```

### ReviewCompleted

Reviewer to scheduler.

```json
{
  "message_type": "review.completed",
  "payload": {
    "subject": "wo_001",
    "decision": "pass",
    "recommended_route": "next_step",
    "confidence": "high",
    "findings": []
  }
}
```

### RouteDecision

Scheduler to runtime.

```json
{
  "message_type": "route.decided",
  "payload": {
    "route": "complete",
    "reason": "All required hard validators passed and no blocking review findings remain."
  }
}
```

### RepairRequest

MetaLoop to Codex goal runtime after verification failure.

```json
{
  "message_type": "repair.requested",
  "payload": {
    "repair_id": "repair_001",
    "failed_checks": [
      "npm-compile"
    ],
    "objective": "Fix TypeScript compile errors without changing MissionSpec scope.",
    "evidence": [
      {
        "type": "artifact_ref",
        "uri": "artifact://run_123/logs/npm-compile.txt"
      }
    ],
    "constraints": [
      "Do not weaken acceptance criteria",
      "Do not remove tests to pass validation"
    ]
  }
}
```

## GoalContract

When MetaLoop submits work to Codex `/goal`, it should include a structured contract inside the natural-language objective.

This contract is a strong instruction, not a hard runtime guarantee.

```json
{
  "schema": "metaloop.goal_contract",
  "version": "1.0",
  "mission_id": "mission_abc",
  "objective": "Build a VS Code extension MVP for visualizing TorchScript graphs.",
  "deliverables": [],
  "constraints": [],
  "out_of_scope": [],
  "definition_of_done": [],
  "validation_commands": [],
  "required_report_path": ".metaloop/execution_report.json"
}
```

Rules for Codex:

- Treat this contract as authoritative.
- Do not weaken acceptance criteria.
- Do not modify the MissionSpec unless explicitly instructed.
- Before marking the goal complete, create the required execution report.
- If validation cannot be run, record exact reasons and evidence.

## ExecutionReport

Codex should write an execution report after goal execution.

The report is candidate evidence. MetaLoop must validate it before trusting it.

```json
{
  "schema": "metaloop.execution_report",
  "version": "1.0",
  "mission_id": "mission_abc",
  "status": "completed",
  "summary": "Implemented the requested MVP.",
  "changed_files": [],
  "validation_results": [],
  "known_limitations": [],
  "evidence": []
}
```

MetaLoop checks:

- Report file exists.
- JSON schema is valid.
- `mission_id` matches.
- Claimed validation results correspond to real command artifacts when available.
- Changed files are within allowed scope.
- Known limitations are reflected in final acceptance classification.

## Codex `/goal` Boundary

MetaLoop may pass `GoalContract` to Codex `/goal`, but `/goal` does not enforce the schema.

Therefore:

```text
GoalContract sent to Codex = strong instruction
ExecutionReport from Codex = candidate evidence
MetaLoop validators/review = final authority
```

Do not design the system so that valid-looking Codex JSON automatically completes a mission.

## Implementation Plan

Initial module:

```text
src/metaloop/messages.py
```

Initial schemas:

- `AgentRef`
- `ArtifactRef`
- `EvidenceRef`
- `AgentMessage`
- `GoalContract`
- `ExecutionReport`
- `WorkOrder`
- `WorkResult`
- `ReviewCompleted`
- `RouteDecision`
- `RepairRequest`

Required tests:

- Valid messages parse.
- Unknown message types are rejected in strict mode.
- Invalid payload for known message type is rejected.
- Artifact refs are accepted instead of inline huge data.
- ExecutionReport must match mission id.

## Non-Goals

- Do not replace user-facing natural-language Co-Design.
- Do not introduce RDF/protobuf before there is a concrete need.
- Do not store huge logs inside message JSON.
- Do not route scheduler decisions by parsing `rationale`.
- Do not treat Codex-generated JSON as trusted without MetaLoop validation.

