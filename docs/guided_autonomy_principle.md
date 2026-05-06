# Guided Autonomy Principle

Last updated: 2026-05-02

## Core Thesis

MetaLoop must not replace agentic exploration with static retrieval.

Modern coding agents such as Codex and Claude Code are highly capable autonomous investigators. They often perform better when they can inspect the workspace, search with `rg`, read files, run tests, observe errors, and adapt their next action dynamically.

MetaLoop should provide:

- Structured intent.
- Explicit authority.
- Permissioned knowledge entrypoints.
- Sandbox and tool boundaries.
- Acceptance and evidence requirements.
- Verification after execution.

MetaLoop should not try to precompute and inject every relevant piece of information as static context.

## Static RAG vs Agentic Retrieval

### Static RAG

```text
system retrieves chunks before reasoning
  -> chunks are inserted into prompt
  -> model answers from supplied context
```

Risks:

- Retrieval can miss the relevant file.
- Embedding similarity may not match engineering relevance.
- Irrelevant chunks pollute attention.
- Static context can become stale.
- The model may not adapt its search path after new observations.

### Agentic Retrieval

```text
agent receives intent, boundaries, and tools
  -> agent searches
  -> observes results
  -> updates plan
  -> reads more or runs tests
  -> acts
```

Strengths:

- Better fit for codebases.
- Search path adapts to observations.
- Tool results are grounded in the current workspace.
- Tests and commands provide feedback.
- The agent can decide what it needs next.

MetaLoop should support agentic retrieval by default.

## Correct Role of SKS

Structured Knowledge System is not a RAG chunk dump.

SKS is:

```text
navigation map + permission layer + provenance system
```

It provides:

- Stable refs.
- Section summaries.
- Entry points.
- Permission checks.
- Content hashes.
- Artifact refs.
- Decision records.

It should not pretend to know all information the agent will need in advance.

## Correct Role of SCP

Structured Context Protocol should compile the minimum starting context, not the complete working memory.

Context packets should include:

- Current objective.
- Intent and constraints.
- Acceptance checks.
- Relevant refs.
- Allowed exploration scope.
- Tool policy.
- Output contract.

They should not include:

- Full repository dumps.
- Full static RAG retrieval results.
- All possibly relevant docs.
- All prior events.

## Exploration Policy

Context packets should include an explicit exploration policy.

Example:

```json
{
  "exploration_policy": {
    "mode": "guided_autonomy",
    "allowed_tools": ["rg", "sed", "git diff", "pytest", "npm test"],
    "preferred_tools": ["rg"],
    "allowed_paths": ["src/metaloop", "tests", "docs"],
    "forbidden_paths": [".env", "secrets", ".metaloop/private"],
    "recommended_entrypoints": [
      "sks://doc/structured_context_protocol#core-thesis",
      "sks://doc/intent_transmission_contract#commander-intent"
    ],
    "search_strategy": [
      "Prefer rg for symbols and tests before broad file reads.",
      "Read only files that are relevant to the current objective.",
      "Run focused validation after edits."
    ]
  }
}
```

## Permission Boundary

Autonomy is not unrestricted access.

The agent may explore within:

- Role.
- Purpose.
- Workspace scope.
- Tool policy.
- File/path permissions.
- Budget.
- Sandbox.

If the agent needs information outside its permission boundary, it should request or report a blocked state rather than bypassing the boundary.

## Output Obligation

Autonomous exploration must be reported back structurally.

The agent should record:

- What it inspected.
- What it changed.
- What commands it ran.
- What evidence supports completion.
- What limitations remain.
- What it could not access.

This feeds AMP, EventStore, ArtifactStore, and Verification.

## Design Rules

### Give Intent, Not Just Chunks

The agent needs purpose, desired end state, and acceptance criteria more than a large pile of retrieved text.

### Give Entry Points, Not Exhaustive Context

Refs are navigation aids. They are not a complete substitute for exploration.

### Give Tools, Not Blind Trust

Allow grep/read/test inside policy. Verify the result afterward.

### Verify Outcomes, Not Every Thought

MetaLoop does not need to micromanage all intermediate reasoning. It needs auditable evidence and final verification.

### Do Not Over-Constrain Intelligent Agents

If the structure prevents the agent from discovering necessary information, the structure is counterproductive.

## Anti-Patterns

- Treating SKS as a static RAG database.
- Injecting top-K chunks as if they are complete truth.
- Preventing the agent from using search tools inside its authorized scope.
- Forcing all relevant information to be predicted before execution.
- Passing only refs without granting any way to resolve or explore them.
- Treating tool-driven exploration as inefficiency instead of intelligence.

## MetaLoop Formula

```text
Structured intent
  + permissioned knowledge entrypoints
  + sandboxed tool autonomy
  + structured evidence
  + independent verification
  = guided autonomy
```

This is the intended model for MetaLoop.

