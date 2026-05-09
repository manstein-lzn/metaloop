# MetaLoop

MetaLoop 是一个本地优先的任务治理层，用来约束和稳定 Codex 驱动的复杂工作。

当前收敛方向：

```text
Codex Skill -> minimal MetaLoop kernel -> persistent Codex agent thread(s) -> Adaptive Goal Loop -> ExecutionReport -> VerificationResult
```

宪法级架构参考见 [docs/mission_capsule_constitution.md](docs/mission_capsule_constitution.md)。它把 Mission Capsule 定义为持久治理对象，并明确生命周期、权限、证据、验收、领域 profile、尝试记忆，以及 repair / redesign / decomposition 的边界。

产品方向：MetaLoop 不再把外部 CLI 编排器作为主智能运行时。Codex agent 保持自然对话、项目理解和长期上下文；MetaLoop skill 和 minimal kernel 负责 Mission Capsule、VerificationSpec、ExecutionReport、VerificationResult、thread registry 和审计状态。现有 CLI 子命令仍保留为 legacy、脚本、CI、调试和 full repo implementation 路径，但复杂项目的推荐心智是：persistent Codex thread agents 通过 `.metaloop/` artifacts 协作。

MetaLoop 的通用方法论正在收敛为 Adaptive Goal Loop：`Goal -> Plan -> Act -> Observe -> Evaluate -> Diagnose -> Decide -> Next Plan`。研究、工程、前端、benchmark、论文复现等任务共享同一闭环；domain extension 只负责定义证据语言、指标、风险和 validators，不在 core 里分裂出一套研究专用流程。

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
- [docs/metaloop_multi_thread_agent_protocol.md](docs/metaloop_multi_thread_agent_protocol.md)：persistent Codex thread agent 协议和 `.metaloop/threads.json` registry。
- [docs/metaloop_clean_library_mission_plan.md](docs/metaloop_clean_library_mission_plan.md)：clean library 第一阶段边界抽取计划。
- [docs/metaloop_final_clean_library_plan.md](docs/metaloop_final_clean_library_plan.md)：final clean library 升级计划和最终 VerificationSpec。
- [docs/metaloop_adaptive_goal_loop.md](docs/metaloop_adaptive_goal_loop.md)：通用目标逼近闭环：Goal / Plan / Observe / Evaluate / Diagnose / Decide / Next Plan。
- [docs/team_internal_preview_guide.md](docs/team_internal_preview_guide.md)：团队内测指南和推广边界。
- [docs/codex_install_metaloop_skill.md](docs/codex_install_metaloop_skill.md)：可直接复制给 Codex 的一键 skill 安装 prompt。
- [docs/release/v0.1.0-alpha.md](docs/release/v0.1.0-alpha.md)：Alpha 发布说明。

## Skill-First 方向

MetaLoop 正在被重定位为 Codex 的 skill-first、not prompt-only 协议层。`$metaloop` skill 是轻量入口和对齐界面；真正负责检查、状态和更强约束的是 bundled scripts、schemas、validators、`.metaloop/` artifacts，以及可选的 hooks / sandbox / wrapper runtime。

## Clean Library 方向

MetaLoop 的库化目标是把可复用协议内核从 legacy full repo CLI/TUI/Codex runtime 中分离出来。`metaloop_core` 是 clean library 边界：它负责 portable `.metaloop/` state、Adaptive Goal Loop state、Mission Capsule I/O、ExecutionReport I/O、ExtensionSpec / VerificationSpec 校验、generic validators、`verify_workspace()`、thread registry、event log、id/time helper 和 repair/redesign vocabulary。`metaloop_core` 不能反向依赖 `metaloop.cli`、Rich UI、TUI shell、Codex exec/SDK adapters、worker 或旧多 agent runtime。

当前分层目标：

```text
metaloop_core     -> reusable protocol/state/verification backend
skills/metaloop   -> self-contained Codex Skill and bundled kernel
metaloop CLI/TUI  -> legacy/devtool/CI/fallback full implementation
```

详细任务计划见 [docs/metaloop_clean_library_mission_plan.md](docs/metaloop_clean_library_mission_plan.md) 和 [docs/metaloop_final_clean_library_plan.md](docs/metaloop_final_clean_library_plan.md)。skill kernel 仍然保持自包含，不要求目标环境先安装完整 package；仓库内通过 core/skill parity tests 防止 portable kernel 与 `metaloop_core` 的状态和验证语义漂移。

复杂项目中可以使用多个持久 Codex thread agent，但共享真相必须落在 `.metaloop/`：

```text
interface thread -> 和用户对话，维持项目目标和下一步判断
design thread    -> 深挖需求，设计 Mission Capsule / VerificationSpec
worker thread    -> 执行 locked capsule，不弱化验收
reviewer thread  -> 独立审查证据和 contract fit
verifier/kernel  -> 按 locked VerificationSpec 做确定性验收
```

bundled kernel 现在提供 `.metaloop/threads.json` registry，用于记录 role、thread_id、职责、状态和 handoff 边界；也提供 `.metaloop/event_log.jsonl`，用于记录长任务中的观察、决策、阻塞、handoff 和验证笔记。thread context 可以保留智能连续性，但 operational truth 仍以 `.metaloop/mission_capsule.json`、locked VerificationSpec、`.metaloop/execution_report.json`、`.metaloop/verification_result.json`、event log 和 attempts/decisions 为准。

仓库内的 skill package 入口是 [skills/metaloop/SKILL.md](skills/metaloop/SKILL.md)，UI metadata 在 [skills/metaloop/agents/openai.yaml](skills/metaloop/agents/openai.yaml)。它被设计为可独立部署的 Codex Skill：最小可移植内核位于 [skills/metaloop/scripts/metaloop_kernel.py](skills/metaloop/scripts/metaloop_kernel.py)，所以目标环境不需要先安装完整 MetaLoop Python package 才能使用 skill 协议。

当前 bundled kernel 包含：

- 最小 design gate。
- locked ExtensionSpec 和 VerificationSpec。
- persistent agent thread registry：`.metaloop/threads.json`。
- lightweight long-task event log：`.metaloop/event_log.jsonl`。
- generic extension package。
- validator `mode` / `severity`。
- capsule / report / spec schema 检查。
- command-based run wrapper。
- hash audit。
- revision archive。
- independent verification。

团队推广建议使用 [docs/codex_install_metaloop_skill.md](docs/codex_install_metaloop_skill.md) 里的 Codex 安装 prompt。它会让 Codex 把自包含 skill package 复制到 `${CODEX_HOME:-$HOME/.codex}/skills/metaloop`，并运行 smoke test。

当前仓库处于 `v0.1.0-alpha` 里程碑，full repo implementation 已经具备：

- 核心 runtime state 的 Pydantic contracts。
- 确定性的 flat dummy runner。
- 多轮 Co-Design 命令，可生成经过 review 的 MissionSpec 文件，包括显式 autonomous Codex Co-Design。
- MissionSpec JSON / YAML 输入。
- Codex-backed runtime role agents：brainstormer、planner、worker、strategy reviewer。
- Codex worker backend，支持 `--output-schema` fallback 和 `--no-output-schema` 模式。
- Rich CLI shell 实验路径，用于 Co-Design、mission selection、run summaries、reviewer findings，以及稳定的脚本友好语义行。
- 结构化终态：`completed`、`failed`、`blocked`、`proposed_next_task`。
- SQLite event / checkpoint 持久化和 artifact validation。
- 极简 v3 contracts：GoalContract、ExecutionReport、VerificationResult。
- Mission compilation、goal-style Codex execution、结构化 `.metaloop/` run files，以及 independent verification。
- 第一版长期运行 `metaloop` shell，使用 Codex SDK-backed UserAgent 和受控 MetaLoop action mapping；该路径保留为 legacy/devtool，不作为复杂项目默认入口。

## 运行测试

```bash
source .venv/bin/activate
pytest -q
```

## Full Repo CLI / Legacy Devtools

复杂项目的推荐入口是 Codex CLI 中的 `$metaloop` skill，并通过 skill-bundled kernel 写入 `.metaloop/` 状态。下面的 full repo CLI 仍可用于本仓库开发、脚本、CI、回归测试和调试，但不再是团队推广的主交互面。

### 运行 Dummy Kernel

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

在 full repo CLI 路径中，运行 `metaloop` 会打开 legacy/experimental workspace shell；也可以显式使用 `metaloop design` 后接 `metaloop run`。交互式 design 默认使用 Codex 作为 co-designer，并提供编号选项和手动输入 fallback。design 命令会写入 `metaloop.mission.json`，run 会自动发现它。

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

交互式 CLI 使用 Rich panels、键盘可选项、prompt-toolkit 编辑器式文本输入，以及持久 run monitor。设计反馈输入支持正常粘贴、历史和光标编辑；`Enter` 提交，`Alt+Enter` 插入换行。执行 `metaloop run` 时，MetaLoop 会保留简洁进度行，用于展示 contract compilation、structured artifacts、Codex turns and commands、verification、reviewer routing、repair attempts 和 final verification。JSON 模式保持纯 machine-readable JSON；普通文本输出保留 `mission:`、`review:`、`next:`、`status:` 等稳定行，方便脚本和快速扫描。

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
