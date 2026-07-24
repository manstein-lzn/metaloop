# Install MetaLoop v3.4 Codex Skill

MetaLoop v3.4 is self-contained. Install only `skills/metaloop/`; no Python package
installation is required.

## Codex Install Request

```text
Install the complete MetaLoop v3.4 Skill directory from skills/metaloop into
${CODEX_HOME:-$HOME/.codex}/skills/metaloop. Replace the existing directory,
remove Python caches, verify the thin kernel and vendored-core parity, then run
a complete v3.4 smoke test in a temporary local Git repository. Do not modify the
current project except for the Skill destination.
```

## Manual Install

```bash
set -euo pipefail

SOURCE=/path/to/metaloop/skills/metaloop
DEST="${CODEX_HOME:-$HOME/.codex}/skills/metaloop"

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$SOURCE" "$DEST"
find "$DEST" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$DEST" -type f -name '*.pyc' -delete

test -f "$DEST/SKILL.md"
test -f "$DEST/scripts/metaloop_kernel.py"
test -f "$DEST/lib/metaloop_core/workspace.py"
test ! -e "$DEST/extensions/generic"
test ! -e "$DEST/references/legacy_v1_compatibility.md"
test ! -e "$DEST/references/v2_governance.md"
```

## Smoke Contract

Create a temporary Git repository with one commit. Run `project init`, then use
`task begin`, edit one managed output, and use `attempt finish`. Confirm automatic
Evidence, approved verification, accepted lifecycle, and passing integrity.
Commit the exact accepted content and confirm Recovery remains fresh/aligned
without a promotion Task. No `recover write` is required.

Also confirm an active dirty Attempt reports `not_yet_reconciled`, a
checkpointed aborted Attempt is carried into the next same-Task Attempt with
path provenance, and narrowing the Contract rejects out-of-scope carried work.

The expected result is schema version `3`, completed Task lifecycle, fresh/aligned
RecoveryView, and passing integrity. A remote repository is not required.
