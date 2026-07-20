from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from metaloop_core.workspace import GitWorkspace, GitWorkspaceError, changed_paths_between, compare_stamps


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "metaloop@example.com")
    _git(repo, "config", "user.name", "MetaLoop Test")
    (repo / ".gitignore").write_text(".metaloop/\n", encoding="utf-8")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    return repo


def test_non_git_workspace_fails_identity_and_returns_unknown_stamp(tmp_path: Path) -> None:
    with pytest.raises(GitWorkspaceError):
        GitWorkspace(tmp_path).identity()
    stamp = GitWorkspace(tmp_path).stamp()
    assert stamp.unknown_reason
    assert compare_stamps(None, stamp) == "unknown"


def test_stamp_tracks_content_not_only_paths_or_mtime(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    adapter = GitWorkspace(repo)
    clean = adapter.stamp()
    assert clean.changed_path_count == 0

    target = repo / "result.bin"
    target.write_bytes(b"one\x00")
    first = adapter.stamp()
    target.write_bytes(b"two\x00")
    second = adapter.stamp()

    assert first.changed_paths == second.changed_paths == ("result.bin",)
    assert first.worktree_digest != second.worktree_digest
    assert changed_paths_between(first, second) == ["result.bin"]
    assert compare_stamps(first, second) == "ahead"


def test_stamp_distinguishes_staged_deleted_and_renamed_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    adapter = GitWorkspace(repo)
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    untracked = adapter.stamp()
    _git(repo, "add", "new.txt")
    staged = adapter.stamp()
    assert untracked.index_digest != staged.index_digest
    assert untracked.content_hash() != staged.content_hash()

    _git(repo, "commit", "-m", "new")
    _git(repo, "mv", "new.txt", "renamed.txt")
    renamed = adapter.stamp()
    assert any("renamed.txt" in path and "new.txt" in path for path in renamed.changed_paths)

    _git(repo, "reset", "--hard", "HEAD")
    (repo / "README.md").unlink()
    deleted = adapter.stamp()
    assert deleted.content_hash() != renamed.content_hash()
    assert "README.md" in deleted.path_state_map()


def test_metaloop_state_is_excluded_and_scan_limits_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    adapter = GitWorkspace(repo)
    clean = adapter.stamp()
    state = repo / ".metaloop" / "projection.json"
    state.parent.mkdir()
    state.write_text("{}", encoding="utf-8")
    assert adapter.stamp().content_hash() == clean.content_hash()

    (repo / "a.txt").write_text("a", encoding="utf-8")
    limited = GitWorkspace(repo, max_paths=0).stamp()
    assert "scan limit" in str(limited.unknown_reason)
    assert compare_stamps(clean, limited) == "unknown"


def test_linked_worktrees_share_repository_but_have_distinct_identity(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    other = tmp_path / "other-worktree"
    _git(repo, "worktree", "add", "-b", "other", str(other))
    primary = GitWorkspace(repo).identity()
    linked = GitWorkspace(other).identity()
    assert primary.repository_root == linked.repository_root
    assert primary.worktree_path != linked.worktree_path


def test_head_change_is_conflicted_not_silently_aligned(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    adapter = GitWorkspace(repo)
    before = adapter.stamp()
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    _git(repo, "add", "change.txt")
    _git(repo, "commit", "-m", "change")
    after = adapter.stamp()
    assert compare_stamps(before, after) == "conflicted"
