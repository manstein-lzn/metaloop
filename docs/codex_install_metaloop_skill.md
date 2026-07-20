# Install MetaLoop Codex Skill

MetaLoop 以 self-contained Codex Skill 交付。目标机器只需要安装仓库中的
`skills/metaloop/`，无需安装完整 Python package。

当前 GitHub 仓库：

```text
git@github.com:manstein-lzn/metaloop.git
```

## 交给 Codex 安装

将下面的请求发送给目标机器上的 Codex：

````text
Install the MetaLoop Codex Skill from GitHub and validate it.

Repository:
git@github.com:manstein-lzn/metaloop.git

Requirements:
1. Install only the self-contained skill package from `skills/metaloop`.
2. Use `${CODEX_HOME:-$HOME/.codex}/skills/metaloop` as the destination.
3. Replace only an existing MetaLoop skill directory.
4. Keep project repositories unchanged and use `/tmp` for smoke-test files.
5. Verify `SKILL.md`, `scripts/metaloop_kernel.py`,
   `extensions/generic/profile.json`, and `lib/metaloop_core/durable.py`.
6. Run `status`, a v1 `design -> run -> verify` smoke test, and a v2 smoke test
   that initializes a Project, creates a Task, and produces a fresh RecoveryView.
7. Confirm the installed directory recursively matches `skills/metaloop` after
   excluding `__pycache__` and `*.pyc`.
8. If permissions or SSH access fail, stop and print the exact manual command.
````

## 手动安装与验证

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
```

V1 compatibility smoke test:

```bash
V1_SMOKE="$(mktemp -d /tmp/metaloop-v1-smoke.XXXXXX)"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$V1_SMOKE" design \
  --intent "Validate installed MetaLoop skill" \
  --rationale "A file proves the lightweight verification flow." \
  --non-goal "Keep project repositories unchanged." \
  --file-exists result.txt
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$V1_SMOKE" run \
  --command "printf 'ok\n' > result.txt"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$V1_SMOKE" verify --json
```

成功结果包含 `"status": "completed_verified"`。

V2 smoke test:

```bash
V2_SMOKE="$(mktemp -d /tmp/metaloop-v2-smoke.XXXXXX)"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$V2_SMOKE" project init
TASK_JSON="$(python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$V2_SMOKE" task create --title "Validate installed MetaLoop v2")"
TASK_ID="$(printf '%s' "$TASK_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$V2_SMOKE" recover write --task "$TASK_ID"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$V2_SMOKE" project integrity

diff -qr \
  --exclude='__pycache__' --exclude='*.pyc' \
  "$WORKDIR/metaloop/skills/metaloop" "$DEST"
```

报告 installed path、v1 verification status、v2 integrity/Recovery freshness，以及是否需要
重启 Codex 才能看到 `$metaloop`。

## 使用

如果当前 session 尚未列出 `$metaloop`，启动一个新 session，然后表达目标：

```text
Use $metaloop. 我想完成 <你的目标>。
```
