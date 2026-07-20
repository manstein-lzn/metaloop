# Codex Install Prompt For MetaLoop Skill

Copy the following prompt into Codex on the target machine.

````text
Install the MetaLoop Codex Skill from GitHub and validate it.

Repository:
git@github.com:manstein-lzn/metaloop.git

Requirements:
1. Do not install the full Python package unless validation requires it.
2. Install only the self-contained skill package from `skills/metaloop`.
3. Use `${CODEX_HOME:-$HOME/.codex}/skills/metaloop` as the destination.
4. If a previous MetaLoop skill exists, replace only that skill directory.
5. Do not modify the current project repository except for temporary smoke-test
   files under `/tmp`.
6. After copying, verify that:
   - `SKILL.md` exists.
   - `scripts/metaloop_kernel.py` exists.
   - `extensions/generic/profile.json` exists.
   - `lib/metaloop_core/durable.py` exists.
   - the kernel can run `status`.
   - a v2 smoke test can initialize a Project, create a Task, and produce a
     fresh RecoveryView.
   - the installed directory recursively matches `skills/metaloop` after
     excluding `__pycache__` and `*.pyc`.
7. If permissions or SSH access fail, stop and print the exact command I should
   run manually.

Suggested commands:

```bash
set -euo pipefail

WORKDIR="$(mktemp -d /tmp/metaloop-skill-install.XXXXXX)"
DEST="${CODEX_HOME:-$HOME/.codex}/skills/metaloop"

git clone git@github.com:manstein-lzn/metaloop.git "$WORKDIR/metaloop"
mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$WORKDIR/metaloop/skills/metaloop" "$DEST"
find "$DEST" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$DEST" -type f -name '*.pyc' -delete

test -f "$DEST/SKILL.md"
test -f "$DEST/scripts/metaloop_kernel.py"
test -f "$DEST/extensions/generic/profile.json"
test -f "$DEST/lib/metaloop_core/durable.py"

python3 "$DEST/scripts/metaloop_kernel.py" --workspace /tmp status

SMOKE="$(mktemp -d /tmp/metaloop-skill-smoke.XXXXXX)"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" project init
TASK_JSON="$(python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" task create --title "Validate installed MetaLoop v2")"
TASK_ID="$(printf '%s' "$TASK_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" recover write --task "$TASK_ID"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" project integrity

diff -qr \
  --exclude='__pycache__' --exclude='*.pyc' \
  "$WORKDIR/metaloop/skills/metaloop" "$DEST"
````

Report:
- installed path
- v2 Project integrity and Recovery freshness
- whether I need to restart Codex for `$metaloop` to appear
```

## After Installation

Start a new Codex session if the current one does not list `$metaloop`.

Try this in any project:

```text
Use $metaloop for this repository. Inspect the project, create or select the
right Task, lock its success contract, and keep the open Attempt recoverable.
```
