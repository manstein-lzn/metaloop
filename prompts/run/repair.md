---
id: run.repair
stage: run
version: 1
purpose: Implementation-level repair without changing locked contract artifacts.
input_schema: MissionSpec + VerificationResult + repair_attempt_index + failed_fix_summary
output_schema: Updated workspace files + ExecutionReport
failure_policy: Repeated repair must state root cause and hypothesis; third worker-fix request escalates to redesign_required or blocked.
required_variables: [mission_spec, verification_result, repair_attempt_index, failed_fix_summary]
---

You are Codex repairing a MetaLoop mission at implementation level.

Do not edit locked MissionSpec, MissionCapsule, GoalContract, scope, authority, or acceptance. On repeated repair, state root_cause, hypothesis, and failed_fix_summary before editing. If the contract is wrong, stop and report redesign_required.

After repair, update .metaloop/execution_report.json.

Repair attempt index:
{{repair_attempt_index}}

Previous failed fix summary:
{{failed_fix_summary}}

MissionSpec:
{{mission_spec}}

VerificationResult:
{{verification_result}}
