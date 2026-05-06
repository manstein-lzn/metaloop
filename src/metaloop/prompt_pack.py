from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_METADATA_FIELDS = ("version", "purpose", "input_schema", "output_schema", "failure_policy")
_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
_UNRESOLVED_PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}", flags=re.DOTALL)


class PromptPackError(ValueError):
    """Raised when a prompt pack file cannot be loaded or rendered safely."""


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    path: Path
    version: str
    metadata: dict[str, Any]
    template_text: str

    @property
    def required_variables(self) -> tuple[str, ...]:
        return tuple(self.metadata.get("required_variables") or ())

    def render(
        self,
        variables: dict[str, Any] | None = None,
        *,
        required_variables: list[str] | tuple[str, ...] | None = None,
    ) -> "RenderedPrompt":
        variables = variables or {}
        required = set(self.required_variables)
        if required_variables:
            required.update(required_variables)
        placeholders = set(_PLACEHOLDER_RE.findall(self.template_text))
        _validate_variables(variables, required | placeholders, required)

        rendered = self.template_text
        for name in sorted(placeholders):
            rendered = rendered.replace(f"{{{{{name}}}}}", str(variables[name]))
        if _UNRESOLVED_PLACEHOLDER_RE.search(rendered):
            raise PromptPackError(f"prompt {self.prompt_id} rendered with unresolved placeholder")
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        return RenderedPrompt(
            prompt_id=self.prompt_id,
            path=self.path,
            version=self.version,
            metadata=dict(self.metadata),
            rendered_text=rendered,
            sha256=digest,
        )


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_id: str
    path: Path
    version: str
    metadata: dict[str, Any]
    rendered_text: str
    sha256: str

    @property
    def hash(self) -> str:
        return self.sha256


def load_prompt_template(prompt_id: str, *, prompt_root: str | Path | None = None) -> PromptTemplate:
    path = _resolve_prompt_path(prompt_id, prompt_root=prompt_root)
    if not path.exists():
        raise PromptPackError(f"prompt file not found: {path}")
    text = path.read_text(encoding="utf-8")
    metadata, body = _parse_prompt_file(text, path=path)
    _validate_metadata(metadata, path=path)
    resolved_id = str(metadata.get("id") or _prompt_id_from_path(path, prompt_root=prompt_root))
    return PromptTemplate(
        prompt_id=resolved_id,
        path=path,
        version=str(metadata["version"]),
        metadata=metadata,
        template_text=body,
    )


def render_prompt(
    prompt_id: str,
    variables: dict[str, Any] | None = None,
    *,
    prompt_root: str | Path | None = None,
    required_variables: list[str] | tuple[str, ...] | None = None,
) -> RenderedPrompt:
    template = load_prompt_template(prompt_id, prompt_root=prompt_root)
    return template.render(variables, required_variables=required_variables)


def _resolve_prompt_path(prompt_id: str, *, prompt_root: str | Path | None) -> Path:
    raw = Path(prompt_id)
    if raw.is_absolute():
        return raw
    if any(part == ".." for part in raw.parts):
        raise PromptPackError(f"prompt id cannot traverse parents: {prompt_id}")

    root = Path(prompt_root).expanduser().resolve() if prompt_root is not None else _default_prompt_root()
    if (root / "prompts").is_dir():
        root = root / "prompts"
    relative = raw if raw.suffix == ".md" else raw.with_suffix(".md")
    return root / relative


def _default_prompt_root() -> Path:
    candidates = [
        Path.cwd() / "prompts",
        Path(__file__).resolve().parents[2] / "prompts",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[-1]


def _prompt_id_from_path(path: Path, *, prompt_root: str | Path | None) -> str:
    root = Path(prompt_root).expanduser().resolve() if prompt_root is not None else _default_prompt_root()
    if (root / "prompts").is_dir():
        root = root / "prompts"
    try:
        return path.resolve().relative_to(root.resolve()).with_suffix("").as_posix()
    except ValueError:
        return path.stem


def _parse_prompt_file(text: str, *, path: Path) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PromptPackError(f"prompt file missing front matter: {path}")
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise PromptPackError(f"prompt file has unterminated front matter: {path}")

    metadata: dict[str, Any] = {}
    for line in lines[1:end_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise PromptPackError(f"invalid metadata line in {path}: {line}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise PromptPackError(f"empty metadata key in {path}")
        metadata[key] = _parse_metadata_value(key, value.strip())
    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    return metadata, body


def _parse_metadata_value(key: str, value: str) -> Any:
    if key == "required_variables":
        return _parse_required_variables(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_required_variables(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError("not a list")
            return _clean_variable_names(parsed)
        except (json.JSONDecodeError, ValueError):
            return _clean_variable_names(stripped[1:-1].split(","))
    return _clean_variable_names(stripped.split(","))


def _clean_variable_names(values: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        name = str(value).strip().strip("'\"")
        if not name:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise PromptPackError(f"invalid required variable name: {name}")
        cleaned.append(name)
    return list(dict.fromkeys(cleaned))


def _validate_metadata(metadata: dict[str, Any], *, path: Path) -> None:
    missing = [key for key in REQUIRED_METADATA_FIELDS if not str(metadata.get(key) or "").strip()]
    if missing:
        raise PromptPackError(f"prompt metadata missing required fields in {path}: {', '.join(missing)}")
    required = metadata.get("required_variables", [])
    if required and not isinstance(required, list):
        raise PromptPackError(f"prompt metadata required_variables must be a list in {path}")


def _validate_variables(variables: dict[str, Any], names: set[str], required: set[str]) -> None:
    for name in sorted(names):
        if name not in variables:
            kind = "required variable" if name in required else "placeholder variable"
            raise PromptPackError(f"missing {kind}: {name}")
        value = variables[name]
        if value is None or (isinstance(value, str) and not value.strip()):
            raise PromptPackError(f"empty variable value: {name}")
