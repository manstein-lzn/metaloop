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

Observability is read-only. Control is explicit. Optional activation is
one-shot and auditable. Workers and optional activators decide when it is safe
to act on control files.

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

The bundled skill includes a minimal read-only local dashboard:

```bash
python3 "$SKILL_DIR/scripts/metaloop_dashboard.py" --workspace . --scope node
python3 "$SKILL_DIR/scripts/metaloop_dashboard.py" --workspace . --scope root
```

It binds to `127.0.0.1:8765` by default, polls the summary endpoint, and exposes
no mutation routes. Keep it on localhost unless you intentionally accept the
risk of exposing local project state.

## Optional Activation

Activation is the smallest automation layer that can remove the user from
routine handoffs without creating a hidden scheduler. It scans node workspaces
once, checks `job_envelope.json`, pending `.metaloop/control/*.json`, and an
activation lease, writes `.metaloop/activation_result.json`, and exits.

The core API is:

```python
from metaloop_core import activate_once, plan_activation
```

The bundled skill kernel exposes:

```bash
python3 "$KERNEL" --workspace . activate --root . --worker-command "<explicit command>"
```

Without `--execute`, activation is dry-run. With `--execute`, it runs only the
explicit worker command supplied by the caller. It does not call Codex by
itself, design tasks, interpret metrics, route work, approve resources, mutate
Mission Capsules, or change locked VerificationSpecs.

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
- No dashboard-owned mutation endpoints
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
