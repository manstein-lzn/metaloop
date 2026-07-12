# Install MetaLoop Codex Skill

MetaLoop 以 self-contained Codex Skill 交付。目标机器只需要安装仓库中的
`skills/metaloop/`，无需安装完整 Python package。

当前发布仓库：

```text
git@github.com:manstein-lzn/metaloop.git
```

## 交给 Codex 安装

将下面的请求发送给目标机器上的 Codex：

```text
Install and validate the MetaLoop Codex Skill from:
git@github.com:manstein-lzn/metaloop.git

Install only `skills/metaloop` into
`${CODEX_HOME:-$HOME/.codex}/skills/metaloop`.
Replace only an existing MetaLoop skill directory. Keep project repositories
unchanged and use `/tmp` for smoke-test files.

Verify SKILL.md, scripts/metaloop_kernel.py, and
extensions/generic/profile.json exist. Then run status and a temporary
design -> run -> verify smoke test. Report the installed path, verification
status, and whether a new Codex session is required.
```

## 手动安装与验证

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
  --rationale "A file proves the lightweight verification flow." \
  --non-goal "Keep project repositories unchanged." \
  --file-exists result.txt
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" run \
  --command "printf 'ok\n' > result.txt"
python3 "$DEST/scripts/metaloop_kernel.py" --workspace "$SMOKE" verify --json
```

成功结果包含：

```text
"status": "completed_verified"
```

## 使用

如果当前 session 尚未列出 `$metaloop`，启动一个新的 Codex session。随后在任意项目中
表达目标即可：

```text
Use $metaloop. 我想完成 <你的目标>。
```

Codex 会读取项目、形成设计、选择验证方式并推进任务；用户无需指定 MetaLoop 的内部
artifact 或协议形态。
