# Intent Transmission Contract Research Notes

Last updated: 2026-05-02

## Purpose

MetaLoop needs a disciplined answer to this question:

```text
What information must be transmitted to an LLM/agent so it can understand the intent, act within authority, and produce verifiable work?
```

This is not only prompt engineering. It overlaps with management, military command, requirements engineering, cybernetics, information theory, human factors, and project governance.

The goal is to extract practical fields for a MetaLoop Intent Transmission Contract.

## 1. Mission Command

Mission Command emphasizes conveying intent rather than micromanaging steps.

Useful concepts:

- Purpose: why the mission matters.
- Key tasks: what must be accomplished.
- Desired end state: what the world should look like after completion.
- Constraints: limits on action.
- Initiative boundary: where the executor may adapt without asking.

MetaLoop implication:

An agent should not only receive `what to do`. It needs:

```text
why this matters
what cannot be skipped
what final state matters
where it may improvise
where it must not improvise
```

Field candidates:

- `commander_intent.purpose`
- `commander_intent.desired_end_state`
- `commander_intent.key_tasks`
- `initiative_boundary.allowed_discretion`
- `initiative_boundary.must_escalate`

## 2. Requirements Engineering

Requirements engineering standards emphasize that requirements should be clear, singular, consistent, feasible, traceable, and verifiable or validatable.

Useful concepts:

- Unambiguous.
- Complete.
- Consistent.
- Singular.
- Necessary.
- Feasible.
- Verifiable / validatable.
- Traceable to source and rationale.

MetaLoop implication:

MissionSpec and ITC requirements should not be free-form wishes.

Each requirement should have:

- Stable id.
- Statement.
- Type.
- Source.
- Rationale.
- Priority.
- Verification method.
- Scope.
- Conflicts/dependencies.

Field candidates:

- `requirements.functional`
- `requirements.non_functional`
- `requirements.constraints`
- `requirements.out_of_scope`
- `requirements.traceability`

## 3. Situation Awareness

Situation awareness research often separates:

- Perception: what facts are present.
- Comprehension: what those facts mean.
- Projection: what may happen next.

MetaLoop implication:

An agent should not receive only the target. It needs current state and risk context.

Field candidates:

- `situation.perception.current_facts`
- `situation.perception.changed_files`
- `situation.perception.failed_validators`
- `situation.comprehension.current_blocker`
- `situation.comprehension.risk_interpretation`
- `situation.projection.likely_next_failures`
- `situation.projection.expected_next_action`

## 4. Grounding and Common Ground

Communication succeeds when sender and receiver establish shared understanding, not when a message is merely sent.

MetaLoop implication:

The system needs explicit understanding checks and ambiguity policies.

Field candidates:

- `understanding_check.must_confirm`
- `understanding_check.ambiguity_policy`
- `understanding_check.block_if_unclear`
- `understanding_check.clarification_refs`

This is especially important after Co-Design and before autonomous execution.

## 5. Goal-Setting Theory

Goal-setting theory emphasizes specific goals, meaningful challenge, commitment, and feedback.

MetaLoop implication:

Avoid vague goals like:

```text
make it good
```

Prefer:

```text
specific target + feedback loop + evidence of completion
```

Field candidates:

- `goal_quality.specific`
- `goal_quality.measurable_or_validatable`
- `goal_quality.feedback_channels`
- `goal_quality.commitment_rule`

## 6. RACI and Responsibility Assignment

RACI clarifies:

- Responsible: does the work.
- Accountable: owns the final result.
- Consulted: provides input.
- Informed: receives status.

MetaLoop implication:

Codex or a worker can be responsible for execution, but MetaLoop verification is accountable for final classification.

Field candidates:

- `responsibility.responsible`
- `responsibility.accountable`
- `responsibility.consulted`
- `responsibility.informed`

This prevents the executor from being the only judge of its own work.

## 7. BDD / Given-When-Then

Behavior-driven development structures acceptance around:

- Given: initial state.
- When: action.
- Then: observable result.

MetaLoop implication:

For product behavior and manual/evidence-based acceptance, Given/When/Then is often clearer than plain text.

Field candidates:

- `acceptance.scenarios[].given`
- `acceptance.scenarios[].when`
- `acceptance.scenarios[].then`
- `acceptance.scenarios[].evidence_required`

## 8. Information Theory

Information reduces uncertainty.

MetaLoop implication:

Context should transmit the minimum information that reduces uncertainty for the current decision or action.

The goal is not maximum context. The goal is maximum relevant uncertainty reduction per token.

Field candidates:

- `uncertainty.current_decision`
- `uncertainty.missing_information`
- `uncertainty.resolution_refs`
- `uncertainty.blocking_unknowns`

## 9. Requisite Variety

Ashby's law of requisite variety says a controller needs enough variety to handle the system it controls.

MetaLoop implication:

Simple tasks need small context. Complex tasks require richer context.

Over-compressing a complex task creates errors. Over-contextualizing a simple task wastes tokens.

Field candidates:

- `complexity.level`
- `complexity.variety_sources`
- `context_depth`
- `required_decision_support`

## 10. Control Loops

Closed-loop systems need:

- Target state.
- Sensor feedback.
- Error signal.
- Controller action.
- Actuator/executor.
- Recheck.

MetaLoop implication:

An agent should know how failure is detected, how feedback is reported, and when to repair or escalate.

Field candidates:

- `feedback_loop.sensors`
- `feedback_loop.error_signals`
- `feedback_loop.repair_policy`
- `feedback_loop.escalation_policy`
- `feedback_loop.completion_policy`

## Integrated Field Set

The practical MetaLoop contract should transmit:

- Identity and role.
- Authority and permissions.
- Purpose.
- Desired end state.
- Key tasks.
- Requirements and constraints.
- Current situation.
- Knowledge access.
- Execution policy.
- Acceptance and evidence.
- Feedback and escalation.
- Output contract.

This is more complete than 5W1H. 5W1H is useful, but insufficient for autonomous execution because it does not fully define authority, validation, evidence, feedback, or information access.

## Working Principle

An agent should be able to answer these questions before acting:

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

If the contract does not answer these questions, autonomous execution is under-specified.

