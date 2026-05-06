# Agent Message Protocol Research Notes

Last updated: 2026-05-02

## Purpose

MetaLoop needs a data format for AI-to-AI and AI-to-code-system communication.

Natural language is useful for user-facing conversation, but it is not sufficient as the primary substrate for autonomous execution because it is hard to validate, diff, route, replay, and audit.

This document records the protocol families MetaLoop should borrow from. It is not a claim that any one existing standard fully solves the problem.

## Findings

### JSON Schema / Pydantic

Best fit for MetaLoop's first implementation.

Strengths:

- Easy for LLMs to generate.
- Easy for Python to validate.
- Versionable.
- Diffable.
- Works with SQLite event logs.
- Can be used for strict output, repair parsers, and rejection paths.

Use for:

- MissionSpec.
- GoalContract.
- ExecutionReport.
- AgentMessage payloads.
- ReviewResult.
- EvidencePacket.
- VerificationResult.

### CloudEvents

Good model for event envelopes.

Strengths:

- Standard fields for event id, source, type, time, data content type, and payload.
- Good for audit and event buses.

Use for:

- MetaLoop system events.
- Cross-process event export.
- Later integration with external observers.

Do not use as the whole agent protocol. It defines event envelopes, not MetaLoop task semantics.

### OpenTelemetry

Good for observability, not task semantics.

Use for:

- Trace spans.
- Metrics.
- Runtime timing.
- Token/tool-call accounting.

Do not use as the core message format for MissionSpec or agent work orders.

### MCP

Useful as a tool/capability boundary.

Strengths:

- Clear separation between model and tools.
- Explicit capabilities.
- Tool schemas.

Use for:

- Thinking about tool registry and capability declarations.
- Future integrations where MetaLoop exposes validators or artifacts as tools.

Do not bind the MetaLoop core protocol to MCP. MetaLoop needs durable mission, acceptance, and audit semantics beyond a tool-call protocol.

### A2A-style Agent Protocols

Useful concepts:

- Agent capability description.
- Task envelope.
- Artifact references.
- Status updates.
- Structured handoff.

Use for:

- Agent-to-agent envelope design.
- Work order lifecycle.
- Artifact references instead of inline huge text.

Do not adopt blindly before the ecosystem stabilizes. MetaLoop's immediate need is local, auditable, Pydantic-friendly contracts.

### Protocol Buffers / Avro

Strong for mature distributed systems, less suitable for early MetaLoop.

Strengths:

- Strict schemas.
- Efficient serialization.
- Good cross-language support.

Weaknesses:

- Harder for LLMs to produce directly.
- Higher iteration cost.
- Less readable during debugging.

Use later only if MetaLoop needs stable multi-language service boundaries.

### JSON-LD / RDF

Useful for knowledge graph semantics, not appropriate for the first implementation.

Strengths:

- Semantic interoperability.
- Linked data.

Weaknesses:

- Complex.
- High cognitive overhead.
- Not necessary for local execution governance.

Do not use for the current protocol core.

## Codex `/goal` Implication

Codex `/goal` currently takes a natural-language objective. It does not define a hard structured output protocol for mission acceptance.

MetaLoop can include structured JSON inside a goal objective, but that is still an instruction to the model, not a runtime-enforced contract.

Therefore:

```text
GoalContract sent to Codex = strong instruction
ExecutionReport produced by Codex = candidate evidence
MetaLoop validators/review = final authority
```

## Recommendation

Define a small MetaLoop-owned protocol:

```text
MetaLoop AMP = JSON/Pydantic typed messages + artifact references + validation rules
```

Keep the first version simple:

- JSON objects.
- Explicit `schema` and `version`.
- Uniform envelope.
- Typed payloads.
- Artifact refs for large data.
- Evidence refs for claims.
- Hard rejection of invalid messages in scheduler-critical paths.

Avoid:

- Free-form natural language as a routing substrate.
- Huge inline logs/diffs.
- Protocols that require specialized infrastructure before they add value.

