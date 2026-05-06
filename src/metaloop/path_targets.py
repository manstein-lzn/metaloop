from __future__ import annotations

import re
from pathlib import Path


_EXTENSIONLESS_FILE_NAMES = {
    ".gitignore",
    "Dockerfile",
    "LICENSE",
    "Makefile",
    "NOTICE",
    "README",
}


def normalize_path_validation_target(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().strip("`\"'")
    if not text:
        return None
    while text.startswith("./"):
        text = text[2:]
    return text


def is_valid_path_validation_target(value: str | None) -> bool:
    text = normalize_path_validation_target(value)
    if not text:
        return False
    if any(char.isspace() for char in text):
        return False
    if any(char in text for char in "<>|*?"):
        return False
    if "://" in text or ":" in text:
        return False
    path = Path(text)
    if path.is_absolute():
        return False
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    if any(not re.fullmatch(r"[\w.-]+", part) for part in parts):
        return False
    if text.endswith("/"):
        return True
    filename = parts[-1]
    if filename in _EXTENSIONLESS_FILE_NAMES:
        return True
    return bool(re.search(r"\.[A-Za-z0-9]{1,12}$", filename))
