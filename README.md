# MetaLoop

MetaLoop is a local-first mission governance layer for Codex-driven work.

Current v3 direction:

```text
MissionSpec -> GoalContract -> Codex goal runtime -> ExecutionReport -> VerificationResult
```

The constitutional architecture reference is [docs/mission_capsule_constitution.md](docs/mission_capsule_constitution.md). It defines Mission Capsule as the durable governance object and sets the invariants for lifecycle, authority, evidence, acceptance, domain profiles, attempt memory, and repair/redesign/decomposition boundaries.

Product direction: the current CLI subcommands are the stable foundation, and the first human-facing long-running `metaloop` shell is now available. The user should be able to stay in one session, describe intent naturally, inspect state, run missions, verify results, and give post-run feedback without memorizing many commands. The shell and user-facing agent must still operate through the same structured `.metaloop/` artifacts and locked Mission Capsule boundaries.

## Project Docs

- [STATE.md](STATE.md): current project state and handoff notes.
- [HANDOFF.md](HANDOFF.md): concise session handoff for continuing development.
- [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md): implementation roadmap.
- [docs/archive/metaloop架构设计.md](docs/archive/metaloop架构设计.md): original architecture design notes.
- [docs/mission_capsule_constitution.md](docs/mission_capsule_constitution.md): constitutional architecture reference.
- [docs/ALPHA_USER_GUIDE.md](docs/ALPHA_USER_GUIDE.md): technical user guide.
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): common runtime issues.
- [docs/codex-sdk能力边界.md](docs/codex-sdk能力边界.md): Codex SDK research notes.
- [docs/codex-sdk集成文档.md](docs/codex-sdk集成文档.md): Codex integration engineering guide.
- [docs/minimal_v3_codex_goal_architecture.md](docs/minimal_v3_codex_goal_architecture.md): minimal v3 Codex goal architecture.
- [docs/metaloop_lightweight_protocol_reframing.md](docs/metaloop_lightweight_protocol_reframing.md): 轻量协议层重定位，以及 Codex Skill 的纪律边界。
- [docs/release/v0.1.0-alpha.md](docs/release/v0.1.0-alpha.md): Alpha release notes.

## Skill-First Direction

MetaLoop is being reframed as a skill-first, not prompt-only, protocol layer for Codex. The `$metaloop` skill is the lightweight entry and alignment surface; bundled scripts, schemas, validators, `.metaloop/` artifacts, and optional hooks/sandbox/wrapper runtime remain responsible for checks, state, and stronger constraints.

The in-repo skill package starts at [skills/metaloop/SKILL.md](skills/metaloop/SKILL.md), with UI metadata in [skills/metaloop/agents/openai.yaml](skills/metaloop/agents/openai.yaml). It is intended to be deployable as a standalone Codex Skill: the portable minimum kernel is bundled at [skills/metaloop/scripts/metaloop_kernel.py](skills/metaloop/scripts/metaloop_kernel.py), so a target environment does not need the full MetaLoop Python package installed just to use the skill protocol.

This repository is currently at the v0.1.0-alpha milestone:

- Pydantic contracts for the core runtime state.
- A deterministic flat dummy runner.
- Multi-round Co-Design command that generates reviewed MissionSpec files, including explicit autonomous Codex Co-Design.
- MissionSpec JSON/YAML input.
- Codex-backed runtime role agents for brainstormer, planner, worker, and strategy reviewer.
- Codex worker backend with `--output-schema` fallback and `--no-output-schema` mode.
- Product-grade Rich CLI shell for Co-Design, mission selection, run summaries, reviewer findings, and stable script-friendly semantic lines.
- Structured terminal states: `completed`, `failed`, `blocked`, `proposed_next_task`.
- SQLite event/checkpoint persistence and artifact validation.
- Minimal v3 contracts: GoalContract, ExecutionReport, VerificationResult.
- Mission compilation, goal-style Codex execution, structured `.metaloop/` run files, and independent verification.
- First-pass long-running `metaloop` shell with a Codex SDK-backed UserAgent and controlled MetaLoop action mapping.

## Run Tests

```bash
source .venv/bin/activate
pytest -q
```

## Run The Dummy Kernel

Without installing the package:

```bash
PYTHONPATH=src python3 -m metaloop run "Create a dummy artifact"
PYTHONPATH=src python3 -m metaloop run "Create a dummy artifact with retry"
PYTHONPATH=src python3 -m metaloop run "Please split this into a next task proposal" --json
```

Or install in editable mode:

```bash
pip3 install -e .
npm install
metaloop
metaloop shell
metaloop design
metaloop run
metaloop compile
metaloop verify
metaloop status
metaloop design --resume
metaloop resume
metaloop run "Create a dummy artifact"
metaloop design --intent "Summarize the project" --deliverable "one paragraph summary" --criterion "summary is present" --output /tmp/mission.json --review-output /tmp/review.json --strict-review --no-interactive
metaloop design --interviewer codex --intent "Create a concise project summary for technical users" --deliverable "summary paragraph" --criterion "summary is present" --output /tmp/codex-mission.json --no-interactive
metaloop design --interviewer codex --autonomous --intent "Create hello.txt containing hello from autonomous co-design" --workspace /tmp/metaloop-workspace --output /tmp/metaloop-workspace/mission.json --review-output /tmp/metaloop-workspace/review.json --no-interactive
metaloop run --mission /tmp/mission.json
metaloop run "Summarize this repository" --worker codex --sandbox read-only
metaloop run "Summarize this repository" --worker codex --sandbox read-only --approval never --no-output-schema
metaloop run --mission examples/repo-summary.mission.json --worker codex --sandbox read-only --approval never --no-output-schema
```

`--no-output-schema` skips Codex CLI `--output-schema` and relies on prompt JSON plus MetaLoop validation. This is useful when a provider supports ordinary `codex exec --json` but fails on the structured-output/Responses path.

For autonomous Co-Design, use `--interviewer codex --autonomous` with a concrete seed `--intent`. MetaLoop runs interviewer/answer/reviewer rounds, requires MissionSpec reviewer approval before writing the mission, and normalizes content-like file tasks toward `file_contains` validation.

For normal use inside a project directory, run `metaloop` to open the workspace shell, or use `metaloop design` followed by `metaloop run` as explicit subcommands. Interactive design uses Codex as the default co-designer and presents numbered options with manual input fallback. The design command writes `metaloop.mission.json`; run auto-discovers it.

When a run uses the Codex backend, MetaLoop calls separate Codex role agents for `brainstormer`, `planner`, `worker`, and `strategy_reviewer`. The scheduler, policy engine, budget checks, validators, and checkpoints remain in MetaLoop as hard control code.

That role pipeline is no longer the default for mission files. In `auto` mode, `metaloop run` compiles the MissionSpec into a GoalContract, sends one goal-style prompt to ordinary `codex exec`, requires Codex to write `.metaloop/execution_report.json`, then MetaLoop independently writes `.metaloop/verification_result.json`.

Use `metaloop run --mode rigorous` or an explicit `--worker` when you want the classic brainstormer/planner/worker/reviewer Kernel path.

The structured runtime files are:

```text
.metaloop/mission.json
.metaloop/goal_contract.json
.metaloop/goal_prompt.md
.metaloop/execution_report.json
.metaloop/verification_result.json
.metaloop/run.json
.metaloop/runs/<run_id>/codex_events.jsonl
```

Token and tool-call budgets are unlimited by default because the default product stance is task completion. Use `--max-tokens` or `--max-tool-calls` only when you intentionally want a hard cap for a specific design, run, or resume.

The interactive CLI uses Rich panels, keyboard-selectable options, readline-backed free-text input, and a persistent run monitor for the human-facing product shell. During `metaloop run`, MetaLoop preserves concise progress lines for contract compilation, structured artifacts, Codex turns and commands, verification, reviewer routing, repair attempts, and final verification. JSON mode remains plain machine-readable JSON, and normal text output keeps stable lines such as `mission:`, `review:`, `next:`, and `status:` for scripts or quick scanning.

`metaloop` without a subcommand opens a persistent workspace console. By default, the shell starts a Codex SDK-backed UserAgent through `@openai/codex-sdk`. MetaLoop keeps one SDK thread alive for the shell session and stores the thread id at `.metaloop/user_agent_thread.json`, so reopening `metaloop` can resume the same Codex agent conversation. The agent can inspect the current project, talk with the user, and translate requests such as "start a design", "continue the previous run", "show why this is blocked", or "I am not satisfied with the result" into explicit MetaLoop actions.

The shell, not the UserAgent, executes actions. Proposed actions are mapped to built-in commands such as `design`, `run`, `status`, `verify`, and `resume`, with confirmation where appropriate. The UserAgent does not directly modify locked MissionSpec, MissionCapsule, or GoalContract; revision/redesign application remains an explicit follow-up flow. Use `metaloop shell --user-agent exec` for the legacy one-shot `codex exec` adapter, or `metaloop shell --user-agent local` only for deterministic debugging without Codex.

To forget only the user-facing Codex conversation for the current workspace:

```bash
metaloop shell --reset-user-agent-thread
```

This removes `.metaloop/user_agent_thread.json` and leaves mission, capsule, run, verification, and attempt history artifacts intact.

Interrupted work can be resumed. `metaloop design --resume` restores the saved Co-Design draft for the workspace. `metaloop resume` restores the latest non-terminal run checkpoint from `.metaloop/runs.sqlite`, or use `metaloop resume <run_id>`. For the v3 structured runtime, use `metaloop resume --mode goal --workspace .`; it reads `.metaloop/run.json` and either reports the terminal VerificationResult or resumes the goal-style run from the structured MissionSpec.

Runs are persisted by default to `.metaloop/runs.sqlite`:

```bash
metaloop list
metaloop show <run_id>
metaloop show <run_id> --events
```

Legacy shorthand for direct intent runs still works when an argument is present:

```bash
metaloop "Create a dummy artifact"
```

Use strict exit codes for automation:

```bash
metaloop run "Please split this into a next task proposal" --strict-exit-code
# completed=0, failed=1, proposed_next_task=2, blocked=3
```

## Current Scope

MetaLoop Kernel does not spawn child MetaLoops. When a task should be split into an independent closed loop, the scheduler ends the current run with a structured `NextTaskProposal`.
