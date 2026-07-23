from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Iterable

from metaloop_core.schemas import ALIGNMENT_STATES, WORKSPACE_STAMP_SCHEMA


class GitWorkspaceError(RuntimeError):
    """A workspace cannot prove its Git identity or mechanical state."""


@dataclass(frozen=True)
class WorkspaceStamp:
    adapter: str
    adapter_version: str
    repository_root: str
    worktree_path: str
    head_oid: str
    index_digest: str
    worktree_digest: str
    changed_paths_digest: str
    changed_path_count: int
    head_tree_digest: str = ""
    head_parent_oids: tuple[str, ...] = ()
    materialized_tree_digest: str = ""
    changed_paths: tuple[str, ...] = ()
    path_states: tuple[tuple[str, str], ...] = ()
    unknown_reason: str | None = None

    @property
    def alignment_safe(self) -> bool:
        return self.unknown_reason is None

    def path_state_map(self) -> dict[str, str]:
        return dict(self.path_states)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": WORKSPACE_STAMP_SCHEMA,
            "version": "1.0",
            "adapter": self.adapter,
            "adapter_version": self.adapter_version,
            "repository_root": self.repository_root,
            "worktree_path": self.worktree_path,
            "head_oid": self.head_oid,
            "index_digest": self.index_digest,
            "worktree_digest": self.worktree_digest,
            "changed_paths_digest": self.changed_paths_digest,
            "changed_path_count": self.changed_path_count,
            "head_tree_digest": self.head_tree_digest,
            "head_parent_oids": list(self.head_parent_oids),
            "materialized_tree_digest": self.materialized_tree_digest,
            "changed_paths": list(self.changed_paths),
            "path_states": {key: value for key, value in self.path_states},
            "unknown_reason": self.unknown_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkspaceStamp":
        if payload.get("schema") != WORKSPACE_STAMP_SCHEMA:
            raise ValueError("invalid WorkspaceStamp schema")
        raw_states = payload.get("path_states", {})
        if not isinstance(raw_states, dict):
            raise ValueError("WorkspaceStamp.path_states must be an object")
        return cls(
            adapter=str(payload.get("adapter") or ""),
            adapter_version=str(payload.get("adapter_version") or ""),
            repository_root=str(payload.get("repository_root") or ""),
            worktree_path=str(payload.get("worktree_path") or ""),
            head_oid=str(payload.get("head_oid") or ""),
            index_digest=str(payload.get("index_digest") or ""),
            worktree_digest=str(payload.get("worktree_digest") or ""),
            changed_paths_digest=str(payload.get("changed_paths_digest") or ""),
            changed_path_count=int(payload.get("changed_path_count") or 0),
            head_tree_digest=str(payload.get("head_tree_digest") or ""),
            head_parent_oids=tuple(str(item) for item in payload.get("head_parent_oids", [])),
            materialized_tree_digest=str(payload.get("materialized_tree_digest") or ""),
            changed_paths=tuple(str(item) for item in payload.get("changed_paths", [])),
            path_states=tuple(sorted((str(key), str(value)) for key, value in raw_states.items())),
            unknown_reason=payload.get("unknown_reason"),
        )

    def content_hash(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class WorkspaceIdentity:
    repository_root: str
    worktree_path: str
    adapter: str = "git"
    adapter_version: str = "1"

    def to_dict(self) -> dict[str, str]:
        return {
            "adapter": self.adapter,
            "adapter_version": self.adapter_version,
            "repository_root": self.repository_root,
            "worktree_path": self.worktree_path,
        }


class GitWorkspace:
    """Deterministic, bounded Git identity and workspace observation adapter."""

    def __init__(self, workspace: str | Path = ".", *, max_paths: int = 2048, max_bytes: int = 8_000_000) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.max_paths = max_paths
        self.max_bytes = max_bytes

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            env=self._base_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "git command failed").strip()
            raise GitWorkspaceError(message[:240])
        return result.stdout

    def _run_bytes(self, *args: str) -> bytes:
        result = subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            env=self._base_env(),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or b"git command failed").decode(errors="replace").strip()
            raise GitWorkspaceError(message[:240])
        return result.stdout

    def _run_with_env(self, env: dict[str, str], *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "git command failed").strip()
            raise GitWorkspaceError(message[:240])
        return result.stdout

    def identity(self) -> WorkspaceIdentity:
        root = Path(self._run("rev-parse", "--show-toplevel").strip()).resolve()
        common_dir = Path(self._run("rev-parse", "--path-format=absolute", "--git-common-dir").strip()).resolve()
        repository_root = common_dir.parent if common_dir.name == ".git" else root
        return WorkspaceIdentity(str(repository_root), str(root))

    def stamp(self) -> WorkspaceStamp:
        try:
            identity = self.identity()
            head = self._head_oid()
            head_tree_digest = self._head_tree_digest(head)
            head_parent_oids = self._head_parent_oids(head)
            index_digest = self._index_digest()
            entries = self._status_entries()
            if len(entries) > self.max_paths:
                raise GitWorkspaceError(f"workspace scan limit exceeded: {len(entries)} paths")
            path_states: dict[str, str] = {}
            total_bytes = 0
            normalized: list[tuple[str, str]] = []
            for status, path, original in entries:
                if _excluded_path(path) and (not original or _excluded_path(original)):
                    continue
                normalized.append((status, path if not original else f"{path} <- {original}"))
                state, consumed = _file_state(self.workspace / path, status, self.max_bytes - total_bytes)
                if status.startswith("u"):
                    state = "unmerged:" + state
                total_bytes += consumed
                if total_bytes > self.max_bytes:
                    raise GitWorkspaceError(f"workspace scan byte limit exceeded: {total_bytes}")
                path_states[path] = state
                if original:
                    original_state, consumed = _file_state(self.workspace / original, "rename-source", self.max_bytes - total_bytes)
                    total_bytes += consumed
                    path_states[original] = original_state
            changed_paths = tuple(sorted(path for _, path in normalized))
            changed_digest = _digest_json(normalized)
            worktree_digest = _digest_json(sorted(path_states.items()))
            materialized_tree_digest = (
                head_tree_digest
                if not normalized and index_digest == head_tree_digest
                else self._materialized_tree_digest(head)
            )
            return WorkspaceStamp(
                adapter=identity.adapter,
                adapter_version=identity.adapter_version,
                repository_root=identity.repository_root,
                worktree_path=identity.worktree_path,
                head_oid=head,
                index_digest=index_digest,
                worktree_digest=worktree_digest,
                changed_paths_digest=changed_digest,
                changed_path_count=len(changed_paths),
                head_tree_digest=head_tree_digest,
                head_parent_oids=head_parent_oids,
                materialized_tree_digest=materialized_tree_digest,
                changed_paths=changed_paths,
                path_states=tuple(sorted(path_states.items())),
            )
        except (GitWorkspaceError, OSError, ValueError) as exc:
            return WorkspaceStamp(
                adapter="git",
                adapter_version="1",
                repository_root=str(self.workspace),
                worktree_path=str(self.workspace),
                head_oid="unknown",
                index_digest="unknown",
                worktree_digest="unknown",
                changed_paths_digest="unknown",
                changed_path_count=0,
                head_tree_digest="unknown",
                materialized_tree_digest="unknown",
                unknown_reason=str(exc)[:240],
            )

    def _head_oid(self) -> str:
        try:
            return self._run("rev-parse", "--verify", "HEAD").strip()
        except GitWorkspaceError:
            return "UNBORN"

    def _index_digest(self) -> str:
        real_index = Path(self._run("rev-parse", "--path-format=absolute", "--git-path", "index").strip())
        with tempfile.TemporaryDirectory(prefix="metaloop-index-") as temporary:
            temporary_root = Path(temporary)
            temporary_index = temporary_root / "index"
            if real_index.is_file():
                shutil.copyfile(real_index, temporary_index)
            with self._isolated_object_environment(temporary_root / "objects") as env:
                env["GIT_INDEX_FILE"] = str(temporary_index)
                if not real_index.is_file():
                    self._run_with_env(env, "read-tree", "--empty")
                tree = self._run_with_env(env, "write-tree").strip()
        return "git-tree:" + tree

    def _head_tree_digest(self, head: str) -> str:
        if head == "UNBORN":
            return "git-tree:" + self._temporary_tree("UNBORN", add_worktree=False)
        return "git-tree:" + self._run("rev-parse", f"{head}^{{tree}}").strip()

    def _head_parent_oids(self, head: str) -> tuple[str, ...]:
        if head == "UNBORN":
            return ()
        value = self._run("show", "-s", "--format=%P", head).strip()
        return tuple(value.split()) if value else ()

    def _materialized_tree_digest(self, head: str) -> str:
        return "git-tree:" + self._temporary_tree(head, add_worktree=True)

    def _temporary_tree(self, head: str, *, add_worktree: bool) -> str:
        with tempfile.TemporaryDirectory(prefix="metaloop-git-") as temporary:
            index_path = Path(temporary) / "index"
            with self._isolated_object_environment(Path(temporary) / "objects") as env:
                env["GIT_INDEX_FILE"] = str(index_path)
                if head == "UNBORN":
                    self._run_with_env(env, "read-tree", "--empty")
                else:
                    self._run_with_env(env, "read-tree", head)
                if add_worktree:
                    self._run_with_env(env, "add", "-A", "--", ".")
                    if head == "UNBORN":
                        self._run_with_env(env, "rm", "-r", "--cached", "--ignore-unmatch", "--", ".metaloop")
                    else:
                        self._run_with_env(env, "reset", "-q", head, "--", ".metaloop")
                return self._run_with_env(env, "write-tree").strip()

    def _base_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_OPTIONAL_LOCKS"] = "0"
        # Pin git output to a deterministic C locale so diagnostics and the
        # actionable errors we surface do not depend on the host LC_ALL.
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        return env

    @contextmanager
    def _isolated_object_environment(self, object_directory: Path | None = None) -> Iterable[dict[str, str]]:
        if object_directory is not None:
            object_directory.mkdir(parents=True, exist_ok=True)
            yield self._object_environment(object_directory)
            return
        with tempfile.TemporaryDirectory(prefix="metaloop-objects-") as temporary:
            path = Path(temporary)
            yield self._object_environment(path)

    def _object_environment(self, temporary_objects: Path) -> dict[str, str]:
        original_objects = self._run("rev-parse", "--path-format=absolute", "--git-path", "objects").strip()
        env = self._base_env()
        alternates = [original_objects]
        if env.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            alternates.append(env["GIT_ALTERNATE_OBJECT_DIRECTORIES"])
        env["GIT_OBJECT_DIRECTORY"] = str(temporary_objects)
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.pathsep.join(alternates)
        return env

    def _status_entries(self) -> list[tuple[str, str, str | None]]:
        raw = self._run_bytes("-c", "core.quotePath=false", "status", "--porcelain=v2", "-z", "--untracked-files=all")
        chunks = raw.split(b"\0")
        entries: list[tuple[str, str, str | None]] = []
        index = 0
        while index < len(chunks):
            chunk = chunks[index]
            index += 1
            if not chunk:
                continue
            text = chunk.decode("utf-8", errors="surrogateescape")
            kind = text[:1]
            if kind == "2":
                fields = text.split(" ", 9)
                path = fields[-1]
                original = chunks[index].decode("utf-8", errors="surrogateescape") if index < len(chunks) else ""
                index += 1
                entries.append((text[:3], path, original or None))
            elif kind in {"1", "u", "?"}:
                maxsplit = 10 if kind == "u" else 8
                path = text.split(" ", maxsplit)[-1] if kind != "?" else text[2:]
                entries.append((text[:3] if kind != "?" else "??", path, None))
        return entries


def workspace_identity(workspace: str | Path = ".") -> WorkspaceIdentity:
    return GitWorkspace(workspace).identity()


def workspace_stamp(workspace: str | Path = ".", **limits: int) -> WorkspaceStamp:
    return GitWorkspace(workspace, **limits).stamp()


def compare_stamps(previous: WorkspaceStamp | None, current: WorkspaceStamp) -> str:
    if current.unknown_reason:
        return "unknown"
    if previous is None:
        return "aligned"
    if previous.repository_root != current.repository_root or previous.worktree_path != current.worktree_path:
        return "conflicted"
    if previous.head_oid != current.head_oid:
        return "aligned" if is_content_preserving_commit(previous, current) else "conflicted"
    if any(value.startswith("unmerged:") for _, value in current.path_states):
        return "conflicted"
    if _same_workspace_state(previous, current):
        return "aligned"
    return "ahead"


def changed_paths_between(previous: WorkspaceStamp | None, current: WorkspaceStamp) -> list[str]:
    if previous is not None and is_content_preserving_commit(previous, current):
        return []
    before = previous.path_state_map() if previous else {}
    after = current.path_state_map()
    return sorted({*before, *after} - {key for key in before if before.get(key) == after.get(key)})


def is_content_preserving_commit(previous: WorkspaceStamp, current: WorkspaceStamp) -> bool:
    if current.unknown_reason or previous.unknown_reason:
        return False
    if previous.repository_root != current.repository_root or previous.worktree_path != current.worktree_path:
        return False
    if not previous.materialized_tree_digest or previous.materialized_tree_digest in {"unknown", "git-tree:"}:
        return False
    return (
        previous.head_oid in current.head_parent_oids
        and current.changed_path_count == 0
        and not current.path_states
        and current.index_digest == current.head_tree_digest
        and previous.materialized_tree_digest == current.head_tree_digest
    )


def alignment_reason(previous: WorkspaceStamp | None, current: WorkspaceStamp) -> str:
    if previous is not None and is_content_preserving_commit(previous, current):
        return "content_preserving_commit"
    return compare_stamps(previous, current)


def _same_workspace_state(previous: WorkspaceStamp, current: WorkspaceStamp) -> bool:
    common_equal = (
        previous.adapter == current.adapter
        and previous.adapter_version == current.adapter_version
        and previous.repository_root == current.repository_root
        and previous.worktree_path == current.worktree_path
        and previous.head_oid == current.head_oid
        and previous.index_digest == current.index_digest
        and previous.worktree_digest == current.worktree_digest
        and previous.changed_paths_digest == current.changed_paths_digest
        and previous.changed_path_count == current.changed_path_count
        and previous.changed_paths == current.changed_paths
        and previous.path_states == current.path_states
    )
    if not common_equal:
        return False
    if previous.materialized_tree_digest and current.materialized_tree_digest:
        return previous.materialized_tree_digest == current.materialized_tree_digest
    return True


def path_allowed(path: str, allowed_paths: Iterable[str]) -> bool:
    allowed_paths = list(allowed_paths)
    if not allowed_paths:
        return True
    normalized = Path(path).as_posix()
    for root in allowed_paths:
        prefix = Path(root).as_posix().rstrip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def _file_state(path: Path, status: str, remaining_bytes: int) -> tuple[str, int]:
    try:
        if path.is_symlink():
            target = os.readlink(path).encode("utf-8", errors="surrogateescape")
            return "symlink:" + hashlib.sha256(target).hexdigest(), 0
        if not path.is_file():
            return "missing", 0
        size = path.stat().st_size
        if size > remaining_bytes:
            raise GitWorkspaceError(f"workspace scan byte limit exceeded by {path.name}: {size}")
        data = path.read_bytes()
        return f"file:{hashlib.sha256(data).hexdigest()}:{len(data)}:{status}", len(data)
    except OSError as exc:
        return "unreadable:" + str(exc)[:80], 0


def _excluded_path(path: str) -> bool:
    parts = Path(path).parts
    return ".metaloop" in parts or ".git" in parts


def _digest_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
