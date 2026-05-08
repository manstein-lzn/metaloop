# MetaLoop

MetaLoop 是一个本地优先的任务治理层，用来约束和稳定 Codex 驱动的复杂工作。

当前 v3 主线：

```text
MissionSpec -> GoalContract -> Codex goal runtime -> ExecutionReport -> VerificationResult
```

宪法级架构参考见 [docs/mission_capsule_constitution.md](docs/mission_capsule_constitution.md)。它把 Mission Capsule 定义为持久治理对象，并明确生命周期、权限、证据、验收、领域 profile、尝试记忆，以及 repair / redesign / decomposition 的边界。

产品方向：现有 CLI 子命令是稳定基础，第一版面向人的长期运行 `metaloop` shell 已经可用。用户应该能留在一个会话里，用自然语言描述意图、查看状态、运行任务、验证结果、提交运行后反馈，而不是记忆大量命令。shell 和 user-facing agent 仍然必须通过同一套结构化 `.metaloop/` artifacts 和 locked Mission Capsule 边界工作。

## 项目文档

- [STATE.md](STATE.md)：当前项目状态和交接备注。
- [HANDOFF.md](HANDOFF.md)：给后续 session 继续开发用的简明交接文档。
- [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)：实现路线图。
- [docs/archive/metaloop架构设计.md](docs/archive/metaloop架构设计.md)：早期架构设计笔记。
- [docs/mission_capsule_constitution.md](docs/mission_capsule_constitution.md)：宪法级架构参考。
- [docs/ALPHA_USER_GUIDE.md](docs/ALPHA_USER_GUIDE.md)：技术用户指南。
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)：常见运行问题。
- [docs/codex-sdk能力边界.md](docs/codex-sdk能力边界.md)：Codex SDK 能力边界研究。
- [docs/codex-sdk集成文档.md](docs/codex-sdk集成文档.md)：Codex 集成工程文档。
- [docs/minimal_v3_codex_goal_architecture.md](docs/minimal_v3_codex_goal_architecture.md)：极简 v3 Codex goal 架构。
- [docs/metaloop_lightweight_protocol_reframing.md](docs/metaloop_lightweight_protocol_reframing.md)：轻量协议层重定位，以及 Codex Skill 的纪律边界。
- [docs/metaloop_dynamic_extension_protocol_upgrade.md](docs/metaloop_dynamic_extension_protocol_upgrade.md)：dynamic ExtensionSpec / VerificationSpec 升级方案和验收标准。
- [docs/team_internal_preview_guide.md](docs/team_internal_preview_guide.md)：团队内测指南和推广边界。
- [docs/codex_install_metaloop_skill.md](docs/codex_install_metaloop_skill.md)：可直接复制给 Codex 的一键 skill 安装 prompt。
- [docs/release/v0.1.0-alpha.md](docs/release/v0.1.0-alpha.md)：Alpha 发布说明。

## Skill-First 方向

MetaLoop 正在被重定位为 Codex 的 skill-first、not prompt-only 协议层。`$metaloop` skill 是轻量入口和对齐界面；真正负责检查、状态和更强约束的是 bundled scripts、schemas、validators、`.metaloop/` artifacts，以及可选的 hooks / sandbox / wrapper runtime。

仓库内的 skill package 入口是 [skills/metaloop/SKILL.md](skills/metaloop/SKILL.md)，UI metadata 在 [skills/metaloop/agents/openai.yaml](skills/metaloop/agents/openai.yaml)。它被设计为可独立部署的 Codex Skill：最小可移植内核位于 [skills/metaloop/scripts/metaloop_kernel.py](skills/metaloop/scripts/metaloop_kernel.py)，所以目标环境不需要先安装完整 MetaLoop Python package 才能使用 skill 协议。

当前 bundled kernel 包含：

- 最小 design gate。
- locked ExtensionSpec 和 VerificationSpec。
- generic extension package。
- validator `mode` / `severity`。
- capsule / report / spec schema 检查。
- command-based run wrapper。
- hash audit。
- revision archive。
- independent verification。

团队推广建议使用 [docs/codex_install_metaloop_skill.md](docs/codex_install_metaloop_skill.md) 里的 Codex 安装 prompt。它会让 Codex 把自包含 skill package 复制到 `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`，并运行 smoke test。

当前仓库处于 `v0.1.0-alpha` 里程碑，已经具备：

- 核心 runtime state 的 Pydantic contracts。
- 确定性的 flat dummy runner。
- 多轮 Co-Design 命令，可生成经过 review 的 MissionSpec 文件，包括显式 autonomous Codex Co-Design。
- MissionSpec JSON / YAML 输入。
- Codex-backed runtime role agents：brainstormer、planner、worker、strategy reviewer。
- Codex worker backend，支持 `--output-schema` fallback 和 `--no-output-schema` 模式。
- 产品级 Rich CLI shell，用于 Co-Design、mission selection、run summaries、reviewer findings，以及稳定的脚本友好语义行。
- 结构化终态：`completed`、`failed`、`blocked`、`proposed_next_task`。
- SQLite event / checkpoint 持久化和 artifact validation。
- 极简 v3 contracts：GoalContract、ExecutionReport、VerificationResult。
- Mission compilation、goal-style Codex execution、结构化 `.metaloop/` run files，以及 independent verification。
- 第一版长期运行 `metaloop` shell，使用 Codex SDK-backed UserAgent 和受控 MetaLoop action mapping。

## 运行测试

```bash
source .venv/bin/activate
pytest -q
```

## 运行 Dummy Kernel

不安装 package 时：

```bash
PYTHONPATH=src python3 -m metaloop run "Create a dummy artifact"
PYTHONPATH=src python3 -m metaloop run "Create a dummy artifact with retry"
PYTHONPATH=src python3 -m metaloop run "Please split this into a next task proposal" --json
```

或者以 editable mode 安装：

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

`--no-output-schema` 会跳过 Codex CLI 的 `--output-schema`，改为依赖 prompt JSON 和 MetaLoop validation。当 provider 支持普通 `codex exec --json`，但 structured-output / Responses 路径失败时，这个模式很有用。

Autonomous Co-Design 使用 `--interviewer codex --autonomous`，并提供具体的 seed `--intent`。MetaLoop 会运行 interviewer / answer / reviewer 多轮流程，要求 MissionSpec reviewer approval 后才写入 mission，并把内容型文件任务规范化到 `file_contains` validation。

在普通项目目录中使用时，运行 `metaloop` 会打开 workspace shell；也可以显式使用 `metaloop design` 后接 `metaloop run`。交互式 design 默认使用 Codex 作为 co-designer，并提供编号选项和手动输入 fallback。design 命令会写入 `metaloop.mission.json`，run 会自动发现它。

当 run 使用 Codex backend 时，MetaLoop 会分别调用 Codex role agents：`brainstormer`、`planner`、`worker`、`strategy_reviewer`。scheduler、policy engine、budget checks、validators 和 checkpoints 仍然留在 MetaLoop 中作为硬控制代码。

这条 role pipeline 已不再是 mission 文件的默认路径。在 `auto` 模式下，`metaloop run` 会把 MissionSpec 编译成 GoalContract，发送一个 goal-style prompt 给普通 `codex exec`，要求 Codex 写入 `.metaloop/execution_report.json`，然后由 MetaLoop 独立写入 `.metaloop/verification_result.json`。

如果需要经典 brainstormer / planner / worker / reviewer Kernel 路径，使用：

```bash
metaloop run --mode rigorous
```

或显式指定 `--worker`。

结构化 runtime 文件包括：

```text
.metaloop/mission.json
.metaloop/goal_contract.json
.metaloop/goal_prompt.md
.metaloop/execution_report.json
.metaloop/verification_result.json
.metaloop/run.json
.metaloop/runs/<run_id>/codex_events.jsonl
```

默认情况下，token 和 tool-call budget 不设上限，因为当前产品立场是优先完成任务。只有当某次 design、run 或 resume 明确需要硬上限时，才使用 `--max-tokens` 或 `--max-tool-calls`。

交互式 CLI 使用 Rich panels、键盘可选项、readline-backed free-text input，以及面向人类产品 shell 的持久 run monitor。执行 `metaloop run` 时，MetaLoop 会保留简洁进度行，用于展示 contract compilation、structured artifacts、Codex turns and commands、verification、reviewer routing、repair attempts 和 final verification。JSON 模式保持纯 machine-readable JSON；普通文本输出保留 `mission:`、`review:`、`next:`、`status:` 等稳定行，方便脚本和快速扫描。

`metaloop` 不带子命令时会打开持久 workspace console。默认情况下，shell 会通过 `@openai/codex-sdk` 启动一个 Codex SDK-backed UserAgent。MetaLoop 会在 shell session 中保持一个 SDK thread，并把 thread id 存到 `.metaloop/user_agent_thread.json`；重新打开 `metaloop` 时可以通过该文件恢复同一个 Codex agent conversation。agent 可以检查当前项目、和用户对话，并把“start a design”、“continue the previous run”、“show why this is blocked”、“I am not satisfied with the result”等请求转换成明确的 MetaLoop actions。

执行 action 的是 shell，不是 UserAgent。Proposed actions 会映射到内置命令，例如 `design`、`run`、`status`、`verify` 和 `resume`，并在合适时要求确认。UserAgent 不会直接修改 locked MissionSpec、MissionCapsule 或 GoalContract；revision / redesign application 仍然是显式后续流程。`metaloop shell --user-agent exec` 可用于旧的一次性 `codex exec` adapter；`metaloop shell --user-agent local` 只用于不依赖 Codex 的确定性调试。

如果只想忘记当前 workspace 的用户侧 Codex conversation：

```bash
metaloop shell --reset-user-agent-thread
```

这会删除 `.metaloop/user_agent_thread.json`，但保留 mission、capsule、run、verification 和 attempt history artifacts。

中断的工作可以恢复。`metaloop design --resume` 会恢复当前 workspace 保存的 Co-Design draft。`metaloop resume` 会从 `.metaloop/runs.sqlite` 恢复最新非终态 run checkpoint，也可以使用 `metaloop resume <run_id>`。对于 v3 structured runtime，使用 `metaloop resume --mode goal --workspace .`；它会读取 `.metaloop/run.json`，并根据当前状态报告终态 VerificationResult 或从结构化 MissionSpec 恢复 goal-style run。

run 默认持久化到 `.metaloop/runs.sqlite`：

```bash
metaloop list
metaloop show <run_id>
metaloop show <run_id> --events
```

直接 intent run 的旧简写在有参数时仍然可用：

```bash
metaloop "Create a dummy artifact"
```

自动化场景可以使用严格 exit codes：

```bash
metaloop run "Please split this into a next task proposal" --strict-exit-code
# completed=0, failed=1, proposed_next_task=2, blocked=3
```

## 当前范围

MetaLoop Kernel 不会 spawn child MetaLoops。当任务应该拆成一个独立闭环时，scheduler 会以结构化 `NextTaskProposal` 结束当前 run。
