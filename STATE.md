# MetaLoop 当前状态

最后更新：2026-07-20

## 一句话状态

MetaLoop v2 已实现为 **Skill-only / SQLite-backed Durable Work Graph**，并保留远端新增的
Progressive Design 与 engineering governance 能力。Skill 负责智能工作纪律，SQLite
负责长期任务中不可依赖聊天上下文的协议事实。

## 当前产品模型

```text
Prompt / Skill       深度设计、Progressive Design、诊断与策略判断
Project docs         项目架构、governing document、module contract、迁移认知
metaloop_core        schema、hash、CAS、事务、验证与恢复状态
.metaloop.db         Project -> Task -> ContractRevision -> Attempt -> Evaluation
Skill package        thin kernel + vendored canonical core
```

## 已实现

- SQLite canonical store、schema migration 和内部引用完整性检查。
- Task parent/dependency graph、repair origin、显式 Task scope 和 CAS。
- Immutable ContractRevision、单 open Attempt、append-only checkpoint/evidence。
- Attempt fingerprint、显式 retry reason 和 sealed content 重算。
- content-bound Evaluation/Review/acceptance chain 与混合 authority 串联。
- evidence 在 seal、verify、review、accept 前重检。
- freshness-checked RecoveryView，包含 dependency heads、current decisions 和
  acceptance chain。
- v1 migration 重新验证内容与 validators，初始化 v2 后旧写命令 fail closed。
- Progressive Design Rule：完整方向、最小端到端切片、显式边界、让步和重访证据。
- V2-native optional governance：显式 change kind、stable inputs、managed outputs、
  allowed paths 和 redesign migration plan，贯穿 Attempt 与 acceptance 生命周期。
- canonical core 生成到 self-contained Skill，portable kernel 保持薄启动器。
- 只读 dashboard、显式 controls 和 v1 read/migration compatibility。

## 稳定边界

- MetaLoop 不是 scheduler、daemon、watcher、agent runtime 或 project manager。
- `.metaloop/metaloop.db` 是 v2 唯一 operational truth；JSON/Markdown 是可重建投影。
- 项目语义与架构正文保留在项目文档，不复制进 core。
- semantic duplicate detection 仍由 agent 判断，代码只处理 exact replay。
- `allowed_paths` 是锁定施工范围声明；强制隔离由 hook、sandbox 或 wrapper 提供。
- observation、control、tick、relay 和 activation 保持显式、one-shot、可审计。

## 当前试用重点

1. open Attempt 中发生上下文压缩时，RecoveryView 是否足够恢复。
2. 同一 Project 多 Task 切换、父子任务和 repair branch 是否自然。
3. fingerprint 是否出现影响真实工作的误报或漏报。
4. DecisionEvent 与恢复投影的信息密度是否合适。
5. Progressive Design 是否降低返工，同时避免设计仪式过重。
6. V2 governance 是否只在 architecture-sensitive 任务中提供净价值。
7. SQLite writer conflict 和显式 Task scope 是否符合真实 multi-thread 使用。

## 当前验证

```bash
python3 tools/sync_skill_core.py
python3 tools/check_skill_core_sync.py
python3 tools/check_core_import_boundary.py
.venv/bin/pytest -q
git diff --check
```

下一阶段以真实试用反馈为准。在同类失败反复出现前，不扩展 scheduler、自动路由、
向量 memory 或复杂 project-management 状态。
