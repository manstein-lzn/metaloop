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
   - the kernel can run `status`.
   - a smoke test can run `design -> run -> verify` and returns
     `completed_verified`.
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

test -f "$DEST/SKILL.md"
test -f "$DEST/scripts/metaloop_kernel.py"
test -f "$DEST/extensions/generic/profile.json"

python3 "$DEST/scripts/metaloop_kernel.py" --workspace /tmp status

SMOKE="$(mktemp -d /tmp/metaloop-skill-smoke.XXXXXX)"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" design \
  --intent "Validate installed MetaLoop skill" \
  --rationale "A file and JSON field prove the lightweight verification flow." \
  --non-goal "Do not rely on agent self-report." \
  --file-exists result.txt \
  --json-field-exists '{"path":"summary.json","field":"held_out.peak1_delta"}'
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" run \
  --command "printf 'ok' > result.txt && printf '{\"held_out\":{\"peak1_delta\":0}}' > summary.json"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" verify --json
````

Report:
- installed path
- smoke verification status
- whether I need to restart Codex for `$metaloop` to appear
```

## After Installation

Start a new Codex session if the current one does not list `$metaloop`.

Try this in any project:

```text
Use $metaloop for this repository. Inspect the project first, then design a
Mission Capsule with ExtensionSpec and VerificationSpec before executing.
```
