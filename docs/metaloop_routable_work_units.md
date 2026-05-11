# MetaLoop Routable Work Units

Date: 2026-05-12

This note defines the minimal cross-node layer proposed for MetaLoop v1.
It stays intentionally small:

- `job_envelope.json` carries a task handoff
- `global_blackboard.json` carries shared facts
- `route_rules.py` or equivalent control code decides the next hop deterministically
- `tick` applies one local effect step and exits
- `relay` moves outbox records to downstream workspaces and exits

## Design Rules

- The envelope is a contract, not a conversation.
- The blackboard is a shared fact registry, not a shared mind.
- The router is deterministic and side-effect free.
- The tick handler is the only place that applies file effects.
- The relay handler is the only place that moves outbox records across workspaces.
- Node intelligence remains inside the local MetaLoop loop.
- Governance happens through hashes, references, and verification results.

## Envelope Shape

The envelope should identify:

- the job
- the assigned role
- the commander intent
- the blackboard reference and hash
- the input capsule reference and hash
- the expected outputs
- the handoff policy

The router should be able to read the envelope and decide the next action
without inspecting chat history.

## Blackboard Shape

The blackboard should hold only stable shared facts:

- project-wide definitions
- locked architectural decisions
- fact records with refs and hashes

Avoid storing free-form discussion or worker reasoning in the blackboard.

## Control Rules

The router should branch on verification status and the latest adaptive
decision, using a small deterministic policy table.

Recommended first-pass actions:

- `completed_verified` -> dispatch downstream
- `failed` + `repair` -> loop back
- `failed` + `redesign` or `pivot` -> route to design or architecture
- `human_acceptance_required` -> suspend
- `unsupported_verification_spec` or `missing_verification_plan` -> route back to design
- `missing_execution_report` or `execution_incomplete` -> wait

## Tick Effects

`tick` is a one-shot effect handler, not a daemon and not a scheduler. It reads
the pure route decision, writes `.metaloop/tick_result.json`, records a small
event, applies one local file effect, and exits.

Recommended first-pass effects:

- `dispatch`: write `.metaloop/outbox/<target>.json`, or write an explicit
  downstream `job_envelope.json` only when the caller provides one
- `loop_back`: write `.metaloop/loop_back_request.json` and mark the local
  capsule `repair_required`
- `route_to`: write `.metaloop/route_to_request.json` and mark the local
  capsule `redesign_required`
- `escalate`: write `.metaloop/blocked.json` and mark the local capsule
  `blocked`
- `suspend`: write `.metaloop/suspended.json`
- `wait`, `diagnose`, or `error`: write a marker file and stop

## Relay Effects

`relay` is a one-shot outbox mover, not a daemon and not a watcher. It scans
`.metaloop/outbox/*.json`, looks up a static dispatch map, and writes the next
workspace's `job_envelope.json` only when an envelope template is explicitly
configured.

Recommended first-pass effects:

- `delivered`: downstream `job_envelope.json` and inbox record were written
- `needs_design`: no template or route was configured, so the next hop must be
  designed explicitly
- `failed`: the template or target workspace was invalid
- `skipped`: the outbox item was already marked delivered

Relay should also write a source-side `relay_result.json` so the delivery can be
audited and replayed.

Tick must not invent downstream mission content. If no explicit downstream
envelope is supplied, dispatch creates an outbox record for a higher-level
orchestrator or human operator to consume.

## Relationship To Existing MetaLoop Artifacts

This layer is an extension of the current protocol, not a replacement for it.

- Mission Capsule remains the local task contract
- VerificationSpec remains the completion gate
- ExecutionReport remains candidate evidence
- VerificationResult remains the final local verdict
- AdaptiveLoop remains the learning loop after each attempt

## Non-Goals

- No super-agent router
- No shared chat memory
- No automatic multi-agent scheduler
- No mutable global brain
- No daemon or hidden polling loop
