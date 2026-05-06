from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from metaloop.schemas import AcceptanceCriteria, MissionSpec, PolicyScope


def load_mission_file(path: str | Path) -> MissionSpec:
    mission_path = Path(path)
    data = _load_mapping(mission_path)
    try:
        return MissionSpec.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid mission file {mission_path}: {exc}") from exc


def build_mission_from_cli(
    *,
    intent: str,
    criterion: str,
    workspace: str,
    mission_file: str | None = None,
) -> MissionSpec:
    if mission_file:
        mission_path = Path(mission_file).expanduser().resolve()
        mission = load_mission_file(mission_path)
        if mission.policy.workspace_root == ".":
            mission.policy.workspace_root = workspace if workspace != "." else str(mission_path.parent)
        return mission
    return MissionSpec(
        intent=intent,
        acceptance_criteria=[AcceptanceCriteria(description=criterion)],
        policy=PolicyScope(workspace_root=workspace),
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Mission file not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        data = _parse_simple_yaml(text)
    else:
        raise ValueError("Mission file must be .json, .yaml, or .yml")
    if not isinstance(data, dict):
        raise ValueError("Mission file root must be an object")
    return data


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by MetaLoop examples.

    This keeps the core package dependency-light while still letting users write
    readable mission files. JSON remains the exact interchange format.
    """

    lines = [_YamlLine(raw) for raw in textwrap.dedent(text).splitlines()]
    lines = [line for line in lines if line.content and not line.content.startswith("#")]
    index = 0

    def parse_block(indent: int) -> Any:
        nonlocal index
        if index >= len(lines):
            return {}
        if lines[index].indent < indent:
            return {}
        if lines[index].content.startswith("- "):
            items = []
            while index < len(lines) and lines[index].indent == indent and lines[index].content.startswith("- "):
                item_text = lines[index].content[2:].strip()
                index += 1
                if not item_text:
                    items.append(parse_block(indent + 2))
                elif ":" in item_text and not _is_quoted_scalar(item_text):
                    key, value = _split_key_value(item_text)
                    item = {key: _parse_scalar(value)}
                    if index < len(lines) and lines[index].indent > indent:
                        child = parse_block(indent + 2)
                        if isinstance(child, dict):
                            item.update(child)
                    items.append(item)
                else:
                    items.append(_parse_scalar(item_text))
            return items

        mapping = {}
        while index < len(lines) and lines[index].indent == indent and not lines[index].content.startswith("- "):
            key, value = _split_key_value(lines[index].content)
            index += 1
            mapping[key] = parse_block(indent + 2) if value == "" else _parse_scalar(value)
        return mapping

    parsed = parse_block(0)
    if not isinstance(parsed, dict):
        raise ValueError("YAML mission root must be a mapping")
    return parsed


class _YamlLine:
    def __init__(self, raw: str) -> None:
        self.indent = len(raw) - len(raw.lstrip(" "))
        self.content = raw.strip()


def _split_key_value(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise ValueError(f"Invalid YAML line: {text}")
    key, value = text.split(":", 1)
    return key.strip(), value.strip()


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _is_quoted_scalar(value: str) -> bool:
    return (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))
