# MetaLoop Troubleshooting

## `codex` Works Locally But MetaLoop Fails With `--output-schema`

Use:

```bash
metaloop run --mission examples/repo-summary.mission.json \
  --worker codex \
  --sandbox read-only \
  --approval never \
  --no-output-schema
```

Reason: `--output-schema` can use a provider/Responses structured-output path that may fail even when ordinary `codex exec --json` works.

## ChatGPT Plugin Sync Warnings

Warnings such as `chatgpt authentication required to sync remote plugins` or Cloudflare HTML in stderr are not necessarily fatal. MetaLoop records them as Codex events or fallback reasons when useful.

## Run Is `blocked`

`blocked` means Codex reported that it needs approval or unavailable sandbox permissions. Re-run with a different sandbox or approval policy only if the task is trusted:

```bash
metaloop run --mission mission.json --worker codex --sandbox workspace-write --approval on-request
```

Avoid `danger-full-access` unless the workspace is externally isolated.

### `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`

This means the Codex CLI bubblewrap sandbox could not initialize networking or loopback in the current Linux environment. MetaLoop did not reject the task; Codex could not run basic commands inside its sandbox.

Resume the blocked run without the bubblewrap sandbox only for a trusted local workspace:

```bash
metaloop resume <run_id> --sandbox danger-full-access --approval never --no-output-schema
```

Also check the workspace. `metaloop run` works in the current directory unless the mission has a concrete `policy.workspace_root`. If the intended project is `~/torchviewer`, run from there:

```bash
cd ~/torchviewer
metaloop run --sandbox danger-full-access --approval never --no-output-schema
```

## Validator Fails

Check the final state:

```bash
metaloop show <run_id> --json
```

Then inspect `review_results`, `failure_report`, and `artifact_validated` events.

## Token Budget Exceeded

MetaLoop's default token budget is unlimited. If a run fails with `token budget exceeded`, the mission or command used an explicit `max_tokens` cap. Resume with a larger cap:

```bash
metaloop resume <run_id> --max-tokens 150000 --no-output-schema
```

You can also start a fresh run with a larger cap:

```bash
metaloop run --max-tokens 150000 --no-output-schema
```

For complex coding tasks, make sure you are in the intended project directory before running. `metaloop run` creates a fresh run id each time; use `metaloop resume <run_id>` to continue a specific checkpoint.

## Tests

```bash
source .venv/bin/activate
pytest -q
```
