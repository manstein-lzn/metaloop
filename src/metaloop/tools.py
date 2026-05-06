from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metaloop.policy import PolicyDecision, PolicyEngine
from metaloop.schemas import Artifact, MissionSpec, RiskLevel


ToolHandler = Callable[[MissionSpec, dict[str, Any]], Artifact]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk_level: RiskLevel
    handler: ToolHandler
    requires_auth: bool = False


class ToolRegistry:
    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"tool not registered: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, mission: MissionSpec, name: str, arguments: dict[str, Any]) -> Artifact:
        spec = self.get(name)
        decision = self.policy_engine.check_tool(mission, spec.name, spec.risk_level)
        if spec.requires_auth:
            decision = PolicyDecision(
                allowed=False,
                reason=f"tool requires human authorization: {name}",
                requires_auth=True,
            )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return spec.handler(mission, arguments)


def make_default_registry(policy_engine: PolicyEngine | None = None) -> ToolRegistry:
    registry = ToolRegistry(policy_engine=policy_engine)
    registry.register(
        ToolSpec(
            name="artifact.echo",
            description="Return a text artifact from the provided content.",
            risk_level=RiskLevel.LOW,
            handler=_echo,
        )
    )
    registry.register(
        ToolSpec(
            name="workspace.write_text",
            description="Write a text file inside the mission workspace.",
            risk_level=RiskLevel.MEDIUM,
            handler=_write_text,
        )
    )
    return registry


def _echo(_mission: MissionSpec, arguments: dict[str, Any]) -> Artifact:
    return Artifact(kind="text", content=str(arguments.get("content", "")))


def _write_text(mission: MissionSpec, arguments: dict[str, Any]) -> Artifact:
    path = arguments.get("path")
    if not path:
        raise ValueError("workspace.write_text requires a path argument")

    policy_engine = PolicyEngine()
    decision = policy_engine.check_workspace_path(mission, Path(path))
    if not decision.allowed:
        raise PermissionError(decision.reason)

    workspace = Path(mission.policy.workspace_root).expanduser().resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = workspace / target
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(arguments.get("content", "")), encoding="utf-8")
    return Artifact(kind="file", uri=str(target), metadata={"tool": "workspace.write_text"})
