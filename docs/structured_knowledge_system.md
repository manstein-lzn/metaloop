# Structured Knowledge System

Last updated: 2026-05-02

## Core Thesis

MetaLoop should not treat documentation, code, run logs, decisions, and artifacts as loose text blobs that are repeatedly copied into prompts.

MetaLoop should maintain a structured, reference-first knowledge system:

```text
Docs / Code / Mission / Events / Artifacts / Decisions / Schemas
  -> Structured Knowledge System
  -> permissioned refs and queries
  -> ContextCompiler
  -> reference-first ContextPacket
  -> LLM runtime
```

The ContextCompiler should not normally inline project knowledge. It should pass stable references, scoped summaries, and excerpts only when needed.

SKS is not a static RAG chunk dump. It is a navigation map, permission layer, and provenance system for agentic exploration. Agents should still be able to inspect files, search with tools, and run validation inside their authorized scope.

See `docs/guided_autonomy_principle.md`.

## Goals

### 1. Reference-First Transmission

If information is already recorded in the structured knowledge system, MetaLoop should pass a reference to it instead of copying the content.

Bad:

```json
{
  "architecture": "Long copied architecture document text..."
}
```

Good:

```json
{
  "refs": [
    {
      "ref": "sks://doc/architecture_v3_goal_runtime#boundary",
      "access": "summary",
      "required": true
    }
  ]
}
```

Inline content is allowed only when:

- The content is small.
- The content is not indexed yet.
- The role needs the exact excerpt now.
- The permission policy allows it.

### 2. Efficient Agent Retrieval

Agents should not rely on bloated context packets to find information.

They should receive:

- Stable refs.
- Section summaries.
- Queryable indexes.
- Explicit access mode: `metadata`, `summary`, `excerpt`, or `full`.

This lets agents request or receive the precise information needed for their role.

This does not mean MetaLoop must predict all information an agent will need. SKS should provide entrypoints and safe resolution paths so the agent can investigate dynamically.

### 3. Permission and Information Isolation

An agent should only see information relevant to its role, objective, and authority.

Information unrelated to the role should be naturally absent from its context packet.

This improves:

- Token efficiency.
- Work focus.
- Security.
- Auditability.
- Role isolation.

## Relationship to SCP and AMP

Structured Knowledge System, Structured Context Protocol, Intent Transmission Contract, and Agent Message Protocol are separate layers.

```text
SKS: where project knowledge lives and how it is referenced/resolved.
ITC: what intent, authority, situation, acceptance, and feedback must be transmitted.
SCP: how minimal role-specific LLM context is compiled from SKS and state.
AMP: how MetaLoop components exchange structured messages and results.
```

Flow:

```text
Source files / docs / events / artifacts
  -> SKS index
  -> permissioned refs
  -> ITC
  -> SCP ContextPacket
  -> LLM
  -> AMP result message
  -> verification and state update
```

## Source Layer

The source layer contains original material.

Examples:

```text
docs/*.md
README.md
ROADMAP.md
STATE.md
DEVELOPMENT_PLAN.md
metaloop.mission.json
src/**
tests/**
.metaloop/runs.sqlite
.metaloop/artifacts/**
```

The source layer is not optimized for LLM input. It is optimized for human editing and durable storage.

## Index Layer

The index layer creates structured handles over source material.

Initial indexes:

```text
.metaloop/index/documents.json
.metaloop/index/code.json
.metaloop/index/artifacts.json
.metaloop/index/decisions.json
.metaloop/index/events.json
.metaloop/index/schemas.json
.metaloop/index/permissions.json
```

Indexes should be rebuildable from source when possible.

### Document Index

Tracks documents, sections, summaries, tags, and visibility.

Example:

```json
{
  "schema": "metaloop.document_index_item",
  "version": "1.0",
  "doc_id": "structured_context_protocol",
  "title": "Structured Context Protocol",
  "path": "docs/structured_context_protocol.md",
  "classification": "internal",
  "tags": ["architecture", "context", "llm-runtime"],
  "content_hash": "sha256:...",
  "sections": [
    {
      "section_id": "core-thesis",
      "title": "Core Thesis",
      "anchor": "#core-thesis",
      "summary": "LLM calls are stateless; context is compiled from durable state.",
      "tags": ["principle"],
      "visibility": {
        "roles": ["planner", "worker", "reviewer", "scheduler"],
        "purposes": ["implementation", "review", "routing"]
      }
    }
  ]
}
```

### Code Index

Tracks files, symbols, modules, ownership, and allowed roles.

Example:

```json
{
  "schema": "metaloop.code_index_item",
  "version": "1.0",
  "path": "src/metaloop/context.py",
  "language": "python",
  "module": "metaloop.context",
  "symbols": [
    {
      "symbol_id": "ContextCompiler",
      "kind": "class",
      "line": 120,
      "summary": "Compiles durable MetaLoop state into role-specific context packets."
    }
  ],
  "classification": "internal",
  "visibility": {
    "roles": ["worker", "reviewer"],
    "purposes": ["implementation", "review"]
  }
}
```

### Artifact Index

Tracks generated logs, reports, screenshots, diffs, and command output.

Example:

```json
{
  "schema": "metaloop.artifact_index_item",
  "version": "1.0",
  "artifact_id": "npm_compile_log",
  "run_id": "run_123",
  "uri": "artifact://run_123/logs/npm_compile.txt",
  "path": ".metaloop/artifacts/run_123/logs/npm_compile.txt",
  "media_type": "text/plain",
  "sha256": "abc123",
  "summary": "TypeScript compile failed with missing type declaration.",
  "classification": "internal",
  "visibility": {
    "roles": ["worker", "reviewer"],
    "purposes": ["repair", "review"]
  }
}
```

### Decision Index

Tracks architecture and product decisions as structured records.

Example:

```json
{
  "schema": "metaloop.decision_record",
  "version": "1.0",
  "decision_id": "decision_goal_runtime_v3",
  "title": "Use Codex /goal as default long-running execution runtime",
  "status": "accepted",
  "summary": "MetaLoop owns mission governance and verification; Codex /goal owns long-running execution.",
  "refs": [
    "sks://doc/architecture_v3_goal_runtime#core-decision"
  ],
  "created_at": "2026-05-02T00:00:00Z"
}
```

## Access Layer

All content resolution should pass through a single access layer.

Suggested API:

```text
KnowledgeStore.resolve(ref, role, purpose, access)
KnowledgeStore.query(selector, role, purpose)
KnowledgeStore.summarize(ref, role, purpose, budget)
KnowledgeStore.excerpt(ref, role, purpose, budget)
KnowledgeStore.check_access(ref, role, purpose, access)
```

The access layer enforces permissions before content is returned.

If denied:

```json
{
  "error": "access_denied",
  "ref": "sks://doc/security_policy#secrets",
  "role": "worker",
  "purpose": "implementation",
  "reason": "Role lacks security_sensitive visibility."
}
```

## Reference Scheme

MetaLoop references should be stable, readable, and typed.

Initial scheme:

```text
sks://doc/<doc_id>#<section_id>
sks://mission/<mission_id>
sks://mission/current#intent
sks://mission/current#constraints
sks://mission/current#acceptance
sks://code/<path>
sks://symbol/<module>/<symbol_id>
sks://artifact/<run_id>/<artifact_id>
sks://event/<run_id>/<event_id>
sks://decision/<decision_id>
sks://schema/<schema_id>
sks://validator/<check_id>
```

Examples:

```json
{
  "refs": [
    "sks://mission/current#constraints",
    "sks://doc/architecture_v3_goal_runtime#boundary",
    "sks://doc/structured_context_protocol#anti-patterns",
    "sks://validator/npm_compile",
    "sks://artifact/run_123/npm_compile_log"
  ]
}
```

## Access Modes

Each ref can be requested at different levels.

```text
metadata: id, title, tags, hash, path, summary availability
summary: short structured summary
excerpt: bounded relevant text slice
full: full content
```

Default should be `summary`, not `full`.

Full content should require a clear role, purpose, and budget reason.

## Permission Model

Permissions are role and purpose based.

Example:

```json
{
  "ref": "sks://file/src/metaloop/storage.py",
  "classification": "internal",
  "allowed_roles": ["worker", "reviewer"],
  "allowed_purposes": ["implementation", "review"],
  "denied_roles": ["co_designer"],
  "content_budget": {
    "default_access": "summary",
    "max_excerpt_chars": 4000
  }
}
```

Core concepts:

- `role`: planner, worker, reviewer, scheduler, co_designer, verifier.
- `purpose`: design, implementation, repair, review, routing, verification, audit.
- `classification`: public, internal, sensitive, secret.
- `access`: metadata, summary, excerpt, full.

Access is granted only if role, purpose, classification, and requested access all pass policy.

## Context Packet Integration

SCP packets should become reference-first.

Example:

```json
{
  "schema": "metaloop.context_packet",
  "version": "1.0",
  "mode": "reference_first",
  "role": "worker",
  "purpose": "repair",
  "objective": {
    "summary": "Fix compile error"
  },
  "refs": [
    {
      "ref": "sks://mission/current#intent",
      "required": true,
      "access": "summary"
    },
    {
      "ref": "sks://mission/current#acceptance",
      "required": true,
      "access": "full"
    },
    {
      "ref": "sks://artifact/run_123/npm_compile_log",
      "required": true,
      "access": "excerpt"
    }
  ],
  "inline": {
    "only_if_not_indexed": []
  },
  "output_contract_ref": "sks://schema/execution_report"
}
```

ContextCompiler behavior:

```text
role + purpose + objective
  -> query KnowledgeStore
  -> select refs
  -> check permissions
  -> resolve summaries/excerpts only when necessary
  -> produce ContextPacket
```

## Rules

### No Inline If Indexed

If content has an SKS ref, do not inline it by default.

### Permission Before Resolution

Always check access before resolving a ref.

### Need-to-Know Selection

Only include refs relevant to the role and current objective.

Need-to-know does not mean no exploration. It means exploration starts from scoped refs and authorized tools instead of unrestricted global context.

### Progressive Disclosure

Default to `metadata` or `summary`. Use `excerpt` or `full` only when needed.

### Artifact over Blob

Large content belongs in the ArtifactStore. Context packets pass artifact refs.

### Stable IDs

Documents, sections, decisions, validators, artifacts, schemas, and events need stable IDs.

### Hash Everything

Refs should carry or resolve to content hashes so an agent's input is auditable.

### Rebuildable Indexes

Indexes should be rebuildable from source when possible. Generated summaries should carry model/tool provenance.

## Agent Isolation Examples

### Worker

Can see:

- Mission intent summary.
- Relevant constraints.
- Assigned files.
- Failure logs.
- Acceptance checks.

Should not see:

- Full Co-Design transcript.
- Unrelated architecture debates.
- Sensitive user notes.
- Unrelated files.

### Reviewer

Can see:

- Mission acceptance.
- Changed file list.
- Diff summary or patch ref.
- Validation evidence.
- Relevant architecture constraints.

Should not see:

- Unrelated workspace content.
- Internal planner deliberation not needed for review.

### Scheduler

Can see:

- Validator status.
- Review decisions.
- Budget state.
- Retry counts.
- Allowed routes.

Should not need:

- Full source files.
- Full logs.
- Full natural-language reasoning.

### Co-Designer

Can see:

- User-provided goals.
- Public or product-level docs.
- Mission design questions.

Should not see:

- Sensitive local files.
- Secrets.
- Unrelated run artifacts.

## Guided Autonomy Boundary

SKS should support this pattern:

```text
agent receives scoped refs
  -> agent searches within allowed paths
  -> agent resolves allowed refs
  -> agent runs allowed commands
  -> agent reports evidence
  -> MetaLoop verifies
```

SKS should not force this pattern:

```text
system retrieves top-K chunks
  -> chunks are treated as complete context
  -> agent cannot inspect beyond them
```

## Failure Modes

### Stale Index

If content hash differs from source, mark the ref stale and rebuild or force direct source validation.

### Missing Ref

If a required ref cannot be resolved, block context compilation instead of silently omitting it.

### Access Denied

If an agent asks for unauthorized content, record the denial as an event. Do not leak the content.

### Overbroad Query

If a query would return too much, require a narrower selector or return summaries only.

### Summary Drift

Generated summaries can be stale or wrong. They must carry provenance and hash of the source they summarize.

## Implementation Plan

Add:

```text
src/metaloop/knowledge.py
```

Initial schemas:

- `KnowledgeRef`
- `KnowledgeItem`
- `DocumentIndexItem`
- `DocumentSection`
- `CodeIndexItem`
- `ArtifactIndexItem`
- `DecisionRecord`
- `SchemaIndexItem`
- `PermissionRule`
- `AccessRequest`
- `AccessDecision`
- `KnowledgeStore`

Initial commands:

```bash
metaloop index
metaloop index --check
metaloop refs
metaloop resolve <ref>
```

Initial tests:

- Document sections receive stable refs.
- Required refs resolve.
- Missing required refs fail context compilation.
- Unauthorized role cannot resolve denied content.
- Default access returns summary, not full content.
- Large artifacts are represented by refs.
- Stale content hash is detected.

## Relation to Product Direction

This system makes MetaLoop less like a prompt orchestrator and more like an AI-oriented project operating system.

Ordinary agent frameworks often do:

```text
collect text -> build prompt -> ask model
```

MetaLoop should do:

```text
index project knowledge
  -> enforce permissions
  -> compile minimal context refs
  -> invoke LLM
  -> validate structured output
  -> update durable state
```
