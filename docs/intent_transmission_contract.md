# Intent Transmission Contract

Last updated: 2026-05-02

## Purpose

The Intent Transmission Contract is MetaLoop's structured answer to:

```text
What must an agent know to understand the mission, act within authority, and produce verifiable work?
```

ITC is not a prompt template. It is a task-control contract compiled from MissionSpec, Structured Knowledge System refs, Structured Context Protocol packets, policy, and verification state.

## Position in the Architecture

```text
MissionSpec
  -> MissionCompiler
  -> IntentTransmissionContract
  -> GoalContract / ContextPacket / WorkOrder
  -> LLM or Codex /goal
  -> ExecutionReport / ReviewResult
  -> MetaLoop verification
```

Relationships:

```text
ITC: what intent, authority, situation, acceptance, and feedback must be transmitted.
SKS: where referenced knowledge lives and how access is controlled.
SCP: how the ITC and refs are compiled into role-specific LLM context.
AMP: how the resulting structured messages and reports are exchanged.
```

## Design Goals

- Remove ambiguity in task intent.
- Make authority and permissions explicit.
- Avoid unnecessary context.
- Separate execution responsibility from final acceptance accountability.
- Make acceptance and evidence explicit.
- Support autonomous repair and escalation.
- Enable structured, auditable LLM calls.

## Contract Skeleton

```json
{
  "schema": "metaloop.intent_transmission_contract",
  "version": "1.0",
  "contract_id": "itc_001",
  "mission_id": "mission_abc",
  "run_id": "run_123",
  "role": {},
  "responsibility": {},
  "commander_intent": {},
  "requirements": {},
  "situation_awareness": {},
  "knowledge_access": {},
  "execution_policy": {},
  "acceptance": {},
  "feedback_loop": {},
  "output_contract": {}
}
```

## 1. Role and Identity

Defines who the agent is for this invocation.

```json
{
  "role": {
    "name": "worker",
    "agent_id": "codex_goal_runtime",
    "capabilities": [
      "edit_workspace_files",
      "run_allowed_commands"
    ],
    "limitations": [
      "cannot weaken MissionSpec acceptance",
      "cannot decide final MetaLoop completion"
    ]
  }
}
```

Why it matters:

- Prevents role confusion.
- Supports information isolation.
- Supports role-specific context compilation.

## 2. Responsibility Assignment

Defines who executes, who judges, who supplies knowledge, and who is notified.

```json
{
  "responsibility": {
    "responsible": ["codex_goal_runtime"],
    "accountable": ["metaloop_verifier"],
    "consulted": ["knowledge_store", "mission_spec"],
    "informed": ["event_store", "user_if_pending_acceptance"]
  }
}
```

Rule:

The executor may report completion, but MetaLoop verification owns final acceptance classification.

## 3. Commander Intent

Defines purpose, key tasks, and end state.

```json
{
  "commander_intent": {
    "purpose": "Give PyTorch users a local way to inspect trusted TorchScript model structure.",
    "desired_end_state": "A VS Code extension can open a trusted traced .pt file and render a readable top-down DAG with node details.",
    "key_tasks": [
      "Register a read-only custom editor for .pt files",
      "Parse TorchScript into versioned JSON",
      "Render DAG and node details",
      "Document setup, limitations, and security assumptions"
    ],
    "success_meaning": "The MVP is locally usable and its limitations are explicit."
  }
}
```

Rule:

If implementation details conflict with commander intent, preserve intent and escalate ambiguity.

## 4. Requirements

Requirements should be singular, traceable, and verifiable or validatable.

```json
{
  "requirements": {
    "functional": [
      {
        "id": "req_custom_editor",
        "statement": "The extension shall register a read-only custom editor for trusted .pt files.",
        "priority": "must",
        "source_ref": "sks://mission/current#deliverables",
        "verification_ref": "sks://validator/package_custom_editor"
      }
    ],
    "non_functional": [
      {
        "id": "req_local_only",
        "statement": "The extension shall not upload model files.",
        "priority": "must",
        "verification_method": "code_review"
      }
    ],
    "constraints": [
      {
        "id": "constraint_workspace_trust",
        "statement": "Parsing must be disabled unless the workspace is trusted."
      }
    ],
    "out_of_scope": [
      {
        "id": "scope_marketplace",
        "statement": "Marketplace publishing is out of scope for the MVP."
      }
    ]
  }
}
```

## 5. Situation Awareness

Defines current state in perception/comprehension/projection layers.

```json
{
  "situation_awareness": {
    "perception": {
      "current_phase": "repair",
      "changed_files": [
        "torchscript-dag-viewer/src/parserService.ts"
      ],
      "failed_validators": [
        "npm_compile"
      ]
    },
    "comprehension": {
      "current_blocker": "TypeScript compile failure",
      "risk_level": "medium",
      "meaning": "Implementation cannot be considered verified until compile passes."
    },
    "projection": {
      "likely_next_failures": [
        "missing vscode type dependency"
      ],
      "expected_next_action": "Inspect compile log, fix source or dependency issue, rerun npm compile."
    }
  }
}
```

## 6. Knowledge Access

Defines what the agent may know and how it should retrieve it.

```json
{
  "knowledge_access": {
    "default_access": "summary",
    "allowed_refs": [
      {
        "ref": "sks://mission/current#acceptance",
        "access": "full",
        "required": true
      },
      {
        "ref": "sks://artifact/run_123/npm_compile_log",
        "access": "excerpt",
        "required": true
      }
    ],
    "forbidden_refs": [
      "sks://doc/private_user_notes"
    ],
    "resolution_policy": "permission_before_resolution"
  }
}
```

Rules:

- If a ref is indexed, pass the ref by default.
- Resolve full content only when role, purpose, and budget justify it.
- Missing required refs block execution.

## 7. Execution Policy

Defines allowed actions, forbidden actions, sandbox, approvals, and budget.

```json
{
  "execution_policy": {
    "allowed_actions": [
      "edit_allowed_workspace_files",
      "run_validation_commands"
    ],
    "forbidden_actions": [
      "weaken_acceptance_criteria",
      "delete_tests_to_pass",
      "write_outside_workspace",
      "upload_model_files"
    ],
    "sandbox": "workspace-write",
    "approval_policy": "never",
    "budget": {
      "max_wall_time_seconds": null,
      "max_tokens": null
    }
  }
}
```

Execution policy should preserve guided autonomy. It should define the sandbox and allowed exploration tools rather than reducing the agent to static retrieval.

```json
{
  "exploration_policy": {
    "mode": "guided_autonomy",
    "allowed_tools": ["rg", "sed", "git diff", "pytest"],
    "allowed_paths": ["src/metaloop", "tests"],
    "forbidden_paths": [".env", ".metaloop/private"],
    "recommended_entrypoints": [
      "sks://mission/current#acceptance"
    ]
  }
}
```

Rule:

The agent may actively investigate inside its authorized scope. It must report what it inspected and provide evidence for completion.

## 8. Acceptance

Defines hard validation, soft review, evidence, and human acceptance.

```json
{
  "acceptance": {
    "hard_validators": [
      {
        "id": "npm_compile",
        "type": "command",
        "cmd": "npm run compile",
        "cwd": "torchscript-dag-viewer",
        "required": true
      }
    ],
    "soft_reviews": [
      {
        "id": "security_review",
        "rubric_ref": "sks://doc/security_review_rubric#torchscript"
      }
    ],
    "evidence_required": [
      {
        "id": "manual_vscode_demo",
        "type": "manual_steps_or_screenshot",
        "required_for": "completed_verified"
      }
    ],
    "human_acceptance": [
      {
        "id": "ui_product_fit",
        "required": false
      }
    ]
  }
}
```

Rule:

If hard validators fail, the mission cannot be `completed_verified`.

## 9. Feedback Loop

Defines when to repair, block, escalate, or complete.

```json
{
  "feedback_loop": {
    "report_schema": "metaloop.execution_report",
    "report_path": ".metaloop/execution_report.json",
    "when_to_repair": [
      "required_hard_validator_failed",
      "execution_report_missing_required_field"
    ],
    "when_to_block": [
      "required_ref_unavailable",
      "permission_denied_for_required_ref",
      "core_acceptance_ambiguous"
    ],
    "when_to_escalate": [
      "user_product_judgment_required",
      "scope_conflict_detected"
    ],
    "when_to_complete": [
      "hard_validators_passed",
      "blocking_review_findings_zero",
      "required_evidence_present_or_classified_as_limitation"
    ]
  }
}
```

## 10. Output Contract

Defines what the agent must return or write.

```json
{
  "output_contract": {
    "required_message_schema": "metaloop.execution_report",
    "required_artifacts": [
      ".metaloop/execution_report.json"
    ],
    "must_include": [
      "changed_files",
      "validation_results",
      "known_limitations",
      "evidence"
    ]
  }
}
```

## Minimal Required Questions

Before an autonomous agent acts, the ITC should answer:

```text
Who am I in this task?
Why does this task matter?
What end state am I trying to create?
What key tasks cannot be skipped?
What is the current situation?
What am I allowed to see?
What am I allowed to change?
What am I forbidden to do?
How will completion be verified?
What evidence must I produce?
What should I do if I cannot proceed?
Who or what is accountable for final acceptance?
```

If the contract cannot answer these questions, the task is under-specified for autonomous execution.

## Relationship to GoalContract

`GoalContract` is the Codex `/goal`-facing subset of ITC.

It should include:

- Commander intent.
- Key requirements.
- Knowledge refs.
- Execution policy summary.
- Definition of done.
- Required report path.

It should not include:

- Sensitive knowledge not needed by the goal runtime.
- Internal MetaLoop scheduler details.
- Full logs or full documents when refs are enough.

## Relationship to ContextPacket

ContextPacket is the role-specific compiled input for one LLM call.

It may include part of the ITC, but it should only include the fields relevant to that invocation.

Example:

- WorkerContextPacket includes intent, relevant requirements, failure state, allowed refs, execution policy, acceptance checks.
- ReviewerContextPacket includes intent, requirements, diff refs, evidence, review rubric.
- SchedulerContextPacket includes acceptance state, review decision, budget state, allowed routes.

## Validation Rules

ITC itself must be validated before execution:

- Required fields present.
- Requirements have ids.
- Hard validators have explicit commands or check definitions.
- Required refs resolve through KnowledgeStore.
- Role has permission to required refs.
- Forbidden actions are not empty for workspace-write tasks.
- Output contract exists.
- Feedback loop has repair/block/escalate rules.

## Anti-Patterns

- Giving only a task title.
- Giving only implementation steps without purpose.
- Giving purpose without desired end state.
- Giving constraints as prose without ids.
- Letting the executor define its own acceptance.
- Treating structured refs as a static RAG replacement for active investigation.
- Preventing the agent from using search/read/test tools inside its authorized scope.
- Passing full docs/logs instead of refs.
- Hiding uncertainty instead of representing it.
- Using "do your best" as a goal.

## Implementation Plan

Add ITC schema to:

```text
src/metaloop/messages.py
```

or split later into:

```text
src/metaloop/intent.py
```

Initial schemas:

- `IntentTransmissionContract`
- `AgentRole`
- `ResponsibilityAssignment`
- `CommanderIntent`
- `RequirementItem`
- `SituationAwareness`
- `KnowledgeAccessPolicy`
- `ExecutionPolicyContract`
- `ExplorationPolicy`
- `AcceptanceContract`
- `FeedbackLoopContract`
- `OutputContract`

Initial tests:

- ITC rejects missing commander intent.
- ITC rejects requirements without ids.
- ITC rejects required refs that do not resolve.
- ITC rejects inaccessible required refs for the target role.
- ITC rejects workspace-write tasks with no forbidden actions.
- ITC for worker/repair roles includes an exploration policy.
- ITC can compile to `GoalContract`.
- ITC can compile to role-specific ContextPacket.
