# MetaLoop Alpha User Guide

MetaLoop Alpha is a local-first single-task closed-loop agent runner. It is ready for technical users who can run a Python CLI and inspect JSON/event logs.

## Install

```bash
cd /home/mansteinl/metaloop
source .venv/bin/activate
pip install -e .
```

## Quick Smoke Test

```bash
metaloop run "Create a dummy artifact"
metaloop list
```

## Everyday Flow

From a project directory:

```bash
metaloop design
metaloop run
```

`metaloop design` starts with your natural-language goal, then uses Codex as the default co-designer to propose concrete choices. When Codex returns options, you can choose by number or pick the final manual-input option. It writes `metaloop.mission.json` in the current workspace by default. `metaloop run` automatically uses the only mission file in the current workspace. If multiple mission files are present, it asks which one to run.

The interactive CLI is a Rich-based product shell. You should see panels for Co-Design, keyboard-selectable suggested answers, prompt-toolkit editor prompts for design feedback, a persistent run monitor while MetaLoop is executing, a mission summary, reviewer findings, and a run summary with plan/reviewer decisions. Design feedback input supports normal paste, cursor editing, and history; Enter submits and Alt+Enter inserts a newline. The run monitor preserves concise progress lines instead of hiding the run behind a single spinner: contract compilation, Codex turns and commands, verification, reviewer routing, repair attempts, and final verification are visible. `--json` output remains plain JSON for scripts. In JSON mode, MetaLoop will not open interactive mission selection; pass `--mission` if a workspace has multiple mission files.

With the Codex backend, runtime roles are separate Codex calls: brainstormer, planner, worker, and strategy reviewer each produce structured output. The MetaLoop scheduler still owns routing, checkpointing, policy, budget checks, and hard validation guards.

## Co-Design A Mission

Scripted mode:

```bash
metaloop design \
  --interviewer rule \
  --intent "Summarize the project for a technical evaluator" \
  --deliverable "one paragraph summary" \
  --criterion "summary is present" \
  --output /tmp/metaloop-summary.mission.json \
  --review-output /tmp/metaloop-summary.review.json \
  --strict-review \
  --no-interactive

metaloop run --mission /tmp/metaloop-summary.mission.json
```

Codex interviewer preview:

```bash
metaloop design \
  --interviewer codex \
  --intent "Create a concise project summary for technical users" \
  --deliverable "summary paragraph" \
  --criterion "summary is present" \
  --output /tmp/metaloop-summary.mission.json \
  --review-output /tmp/metaloop-summary.review.json \
  --no-interactive
```

Autonomous Codex Co-Design:

```bash
tmpdir=$(mktemp -d /tmp/metaloop-autonomous-XXXX)

metaloop design \
  --interviewer codex \
  --autonomous \
  --intent "Create hello.txt containing hello from autonomous co-design" \
  --workspace "$tmpdir" \
  --output "$tmpdir/mission.json" \
  --review-output "$tmpdir/review.json" \
  --no-interactive

metaloop run --mission "$tmpdir/mission.json" \
  --worker codex \
  --sandbox workspace-write \
  --approval never \
  --no-output-schema \
  --skip-git-repo-check
```

When a mission file contains `policy.workspace_root`, `metaloop run --mission ... --worker codex` uses that workspace as Codex's working directory. You do not need to repeat `--workspace "$tmpdir"` unless you are overriding a mission whose workspace is `"."`.

Interactive mode:

```bash
metaloop design
```

Co-Design runs a loop: interviewer questions, answers, draft updates, MissionSpec review, and follow-up questions until the reviewer converges or the round limit is reached. Use `--strict-review` to block mission generation when the reviewer finds blocking issues.

Co-Design defaults:

- Interactive default: `metaloop design` uses Codex as a co-designer after the initial goal, with numbered options plus manual input.
- Scripted default: `metaloop design --no-interactive` uses the rule interviewer unless you explicitly pass `--interviewer codex`.
- Safe Codex mode: Codex may suggest follow-up questions or enrich optional MissionSpec context. It cannot define or overwrite core fields (`intent`, `deliverables`, `acceptance_criteria`).
- Explicit autonomous mode: add `--autonomous` to let Codex complete core MissionSpec fields from the initial `--intent` seed. In `--no-interactive` mode, Codex also answers reviewer follow-up questions until the MissionSpec converges or `--max-design-rounds` is reached. Autonomous mode requires reviewer approval before the mission file is written.

Codex Co-Design does not execute the mission and does not control Kernel scheduling. It creates a MissionSpec; `metaloop run` executes that spec afterward.

## Run Codex In Read-Only Mode

```bash
metaloop run --mission examples/repo-summary.mission.json \
  --worker codex \
  --sandbox read-only \
  --approval never \
  --no-output-schema
```

Use `--no-output-schema` when the provider supports ordinary `codex exec --json` but fails on the structured-output path.

## Run A Workspace-Write Task

```bash
mkdir -p /tmp/metaloop-alpha-workspace
cp examples/create-file.mission.yaml /tmp/metaloop-alpha-workspace/mission.yaml

metaloop run --mission /tmp/metaloop-alpha-workspace/mission.yaml \
  --workspace /tmp/metaloop-alpha-workspace \
  --worker codex \
  --sandbox workspace-write \
  --approval never \
  --no-output-schema \
  --skip-git-repo-check
```

The file validator checks that `hello.txt` exists before the run can complete.
For content-sensitive file tasks, use `--file-contains "hello.txt::expected text"` or let autonomous Co-Design generate `file_contains` criteria.

Command validators are disabled by default. A mission must explicitly include `validator.command` in `policy.allowed_tools` before `validation_type: command` can run.

You can also generate that mission through Co-Design:

```bash
tmpdir=$(mktemp -d /tmp/metaloop-codesign-XXXX)

metaloop design \
  --intent "Create hello.txt containing hello from co-design" \
  --deliverable hello.txt \
  --file-exists hello.txt \
  --workspace "$tmpdir" \
  --output "$tmpdir/mission.json" \
  --review-output "$tmpdir/review.json" \
  --strict-review \
  --no-interactive

metaloop run --mission "$tmpdir/mission.json" \
  --worker codex \
  --sandbox workspace-write \
  --approval never \
  --no-output-schema \
  --skip-git-repo-check
```

## Inspect Runs

```bash
metaloop list
metaloop show <run_id>
metaloop show <run_id> --events
metaloop show <run_id> --json
```

Normal text output keeps stable semantic lines such as `mission:`, `review:`, `next:`, and `status:` so you can scan logs or write simple shell checks without depending on Rich box drawing.

## Resume Interrupted Work

Resume Co-Design in the current workspace:

```bash
metaloop design --resume
```

Resume the latest non-terminal run checkpoint:

```bash
metaloop resume
metaloop resume <run_id>
```

Run resume uses the latest MetaLoop checkpoint from `.metaloop/runs.sqlite`. If the interruption happened inside a single Codex call, MetaLoop resumes from the last durable checkpoint and may retry that step rather than continuing inside the exact same Codex turn.

Token and tool-call budgets are unlimited by default so MetaLoop can pursue task completion. Use `--max-tokens` or `--max-tool-calls` only when you deliberately want a hard cap:

```bash
metaloop run --max-tokens 150000 --no-output-schema
metaloop resume <run_id> --max-tokens 150000 --no-output-schema
```

Plain `metaloop run` creates a fresh run id each time. Use `metaloop resume <run_id>` when you want to continue a specific interrupted or budget-exhausted run.

## Exit Codes

```bash
metaloop run "Please split this into a next task proposal" --strict-exit-code
```

- `0`: completed, or non-strict non-failure terminal state.
- `1`: failed.
- `2`: proposed next task.
- `3`: blocked.

## Known Limits

- Kernel does not recursively spawn child MetaLoops.
- Co-Design supports deterministic rule interviewing, safe Codex interviewing, and explicit autonomous Codex MissionSpec completion.
- Codex is a worker backend; Scheduler, Policy, Event Log, Checkpoint and Validation stay in MetaLoop.
- `--output-schema` may fail with some providers; use `--no-output-schema`.
- This is a technical Alpha. The CLI now has a product-grade shell, but it is not yet a full-screen TUI or packaged desktop app.
