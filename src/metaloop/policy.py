from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from metaloop.schemas import BudgetUsage, MissionSpec, RiskLevel


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str = ""
    requires_auth: bool = False


class PolicyEngine:
    """Hard-constraint checks that do not depend on an LLM."""

    def check_budget(self, mission: MissionSpec, usage: BudgetUsage) -> PolicyDecision:
        budget = mission.budget
        if budget.max_tokens is not None and usage.tokens > budget.max_tokens:
            return PolicyDecision(allowed=False, reason="token budget exceeded")
        if usage.usd > budget.max_usd:
            return PolicyDecision(allowed=False, reason="usd budget exceeded")
        if budget.max_tool_calls is not None and usage.tool_calls > budget.max_tool_calls:
            return PolicyDecision(allowed=False, reason="tool call budget exceeded")
        if usage.replan_count > budget.max_replan_count:
            return PolicyDecision(allowed=False, reason="replan budget exceeded")
        return PolicyDecision(allowed=True)

    def check_tool(self, mission: MissionSpec, tool_name: str, risk_level: RiskLevel) -> PolicyDecision:
        policy = mission.policy
        if tool_name in policy.denied_tools:
            return PolicyDecision(allowed=False, reason=f"tool denied by policy: {tool_name}")
        if policy.allowed_tools and tool_name not in policy.allowed_tools:
            return PolicyDecision(allowed=False, reason=f"tool not in allowed tool scope: {tool_name}")
        if tool_name in policy.requires_human_auth_for or risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            return PolicyDecision(
                allowed=False,
                reason=f"tool requires human authorization: {tool_name}",
                requires_auth=True,
            )
        return PolicyDecision(allowed=True)

    def check_workspace_path(self, mission: MissionSpec, candidate: str | Path) -> PolicyDecision:
        workspace = Path(mission.policy.workspace_root).expanduser().resolve()
        target = Path(candidate).expanduser()
        if not target.is_absolute():
            target = workspace / target
        target = target.resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return PolicyDecision(
                allowed=False,
                reason=f"path escapes workspace: {target} is outside {workspace}",
            )

        return PolicyDecision(allowed=True)
