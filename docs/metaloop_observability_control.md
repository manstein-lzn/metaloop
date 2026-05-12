# MetaLoop Observability And Control

Date: 2026-05-12

MetaLoop must not become a black box. The system should be observable through
files and controllable through explicit user intent files, without turning the
dashboard or observer into a second scheduler.

## Principle

```text
Dashboard reads truth.
Control writes intent.
Worker acts at safe points.
Kernel verifies outcome.
```

Observability is read-only. Control is explicit. Workers and optional
activators decide when it is safe to act on control files.

## Read-Only Observability

The observer reads existing artifacts:

- `.metaloop/mission_capsule.json`
- `.metaloop/execution_report.json`
- `.metaloop/verification_result.json`
- `.metaloop/adaptive_loop.json`
- `.metaloop/event_log.jsonl`
- `.metaloop/tick_result.json`
- `.metaloop/relay_result.json`
- `.metaloop/outbox/*.json`
- `.metaloop/inbox/*.json`
- `job_envelope.json`

It returns `NodeSummary` or `GlobalSummary` objects. It does not write files,
route work, start workers, mutate capsules, or approve resources.

The core API is:

```python
from metaloop_core import observe_node, observe_root
```

Recommended first UI: a read-only dashboard or terminal command that renders
these summaries.

## Explicit Control Files

Human control should be written as intent files under:

```text
.metaloop/control/
```

Supported first-pass controls:

- `halt.json`: request a soft stop at the next safe point.
- `resource_approval.json`: approve bounded resource usage.
- `inject_fact.json`: add a human fact or prior that a worker/agent should
  process.
- `revise_contract_request.json`: request redesign of the locked contract.

The core API is:

```python
from metaloop_core import write_control_request, pending_control_requests
```

Writing a control request appends an event log entry. It does not directly kill
processes or modify Mission Capsules.

## Safe-Point Rule

Workers and optional activators must check pending controls before:

- starting expensive work
- starting a new attempt
- dispatching a downstream envelope
- consuming a newly delivered envelope
- marking completion

Default behavior should be soft halt. Hard interruption requires a separate
process manager with leases and must write an interruption artifact.

## Non-Goals

- No hidden scheduler
- No automatic daemon in core
- No dashboard-owned routing logic
- No direct mutation of locked VerificationSpec
- No implicit approval for expensive resources

## StateTune Implication

For StateTune-like research, observability should make these visible at all
times:

- current best MAPE, dataset, split, baseline, and run id
- active hypothesis and current plan
- latest diagnosis and next plan
- pending GPU/resource approvals
- leakage/subset/promotion risks
- current outbox/inbox handoffs

The user should be able to observe and intervene like a CTO or research lead,
without reading raw agent chat logs.
