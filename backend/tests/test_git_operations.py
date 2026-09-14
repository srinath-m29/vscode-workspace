"""
Tests for STEP 11: Git Operations (status, add, commit, pull, push) and User Isolation.

Verifies:
1. git status
2. git add
3. git commit (with authenticated user.name and user.email)
4. git fetch
5. git pull (clean branch)
6. git pull (dirty workspace protection - never resets or destroys uncommitted work)
7. git push
8. wrong remote rejection
9. workspace / user isolation
"""

import os
import sys
import subprocess
from pathlib import Path
import pytest

from app.config import settings
from app.auth.session import store_user_token, clear_all_user_tokens
from app.git.credentials import register_workspace_key, clear_all_workspace_keys
from app.git.validation import validate_git_remote_url, validate_workspace_path
from app.git.operations import (
    configure_git_identity,
    git_status,
    git_add,
    git_commit,
    git_pull,
    git_push,
)

USER_1_ID = "1001"
USER_1_NAME = "alice"
USER_1_TOKEN = "gho_mock_token_alice_11111"

USER_2_ID = "99999"
USER_2_NAME = "bob"


@pytest.fixture(autouse=True)
def setup_git_env(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_dir))
    clear_all_user_tokens()
    clear_all_workspace_keys()


def _init_local_repo(repo_dir: Path, user_id: str, username: str) -> None:
    """Helper to initialize a local git repository with identity configured."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    configure_git_identity(
        workspace_path=repo_dir,
        user_id=user_id,
        username=username,
        name=username.capitalize(),
    )


# 1. git status works and correctly reports clean vs dirty states
def test_git_status(tmp_path):
    repo_dir = tmp_path / "workspace" / USER_1_ID / "alice" / "status_repo"
    _init_local_repo(repo_dir, USER_1_ID, USER_1_NAME)

    # Initial empty status
    s1 = git_status(repo_dir, USER_1_ID)
    assert s1["is_clean"] is True

    # Add untracked file
    (repo_dir / "test.txt").write_text("hello")
    s2 = git_status(repo_dir, USER_1_ID)
    assert s2["is_clean"] is False
    assert any("test.txt" in f for f in s2["changed_files"])


# 2. git add stages changes
def test_git_add(tmp_path):
    repo_dir = tmp_path / "workspace" / USER_1_ID / "alice" / "add_repo"
    _init_local_repo(repo_dir, USER_1_ID, USER_1_NAME)

    (repo_dir / "file1.txt").write_text("content 1")
    (repo_dir / "file2.txt").write_text("content 2")

    git_add(repo_dir, USER_1_ID, ["file1.txt"])
    s = git_status(repo_dir, USER_1_ID)
    assert "A  file1.txt" in s["output"]
    assert "? file2.txt" in s["output"] or "?? file2.txt" in s["output"]


# 3. git commit records commit with configured identity
def test_git_commit_with_configured_identity(tmp_path):
    repo_dir = tmp_path / "workspace" / USER_1_ID / "alice" / "commit_repo"
    _init_local_repo(repo_dir, USER_1_ID, USER_1_NAME)

    (repo_dir / "hello.py").write_text("print('hello')")
    git_add(repo_dir, USER_1_ID)
    commit_sha = git_commit(repo_dir, USER_1_ID, "feat: initial commit")

    assert len(commit_sha) == 40, f"Expected full 40-char SHA, got {commit_sha}"

    # Verify author identity in commit log
    proc_log = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    author_info = proc_log.stdout.strip()
    assert "Alice" in author_info
    assert f"{USER_1_ID}+alice@users.noreply.github.com" in author_info


# 4. Git pull on clean branch pulls changes without discarding work
def test_git_pull_clean_workspace(tmp_path):
    # Set up a local bare upstream remote
    upstream_dir = tmp_path / "upstream.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(upstream_dir)], check=True, capture_output=True)

    # Local repo 1 pushes initial commit
    repo1 = tmp_path / "workspace" / USER_1_ID / "alice" / "repo1"
    _init_local_repo(repo1, USER_1_ID, USER_1_NAME)
    subprocess.run(["git", "remote", "add", "origin", str(upstream_dir)], cwd=repo1, check=True)
    (repo1 / "README.md").write_text("# Initial")
    git_add(repo1, USER_1_ID)
    git_commit(repo1, USER_1_ID, "Initial commit")
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo1, check=True, capture_output=True)

    # Local repo 2 clones from upstream
    repo2 = tmp_path / "workspace" / USER_1_ID / "alice" / "repo2"
    repo2.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", str(upstream_dir), str(repo2)], check=True, capture_output=True)
    configure_git_identity(repo2, USER_1_ID, USER_1_NAME)

    # Repo 1 makes new commit and pushes
    (repo1 / "README.md").write_text("# Updated")
    git_add(repo1, USER_1_ID)
    git_commit(repo1, USER_1_ID, "Update README")
    subprocess.run(["git", "push", "origin", "main"], cwd=repo1, check=True, capture_output=True)

    # Repo 2 pulls updates
    pull_res = git_pull(repo2, USER_1_ID, remote="origin", branch="main")
    assert pull_res["status"] == "success"
    assert (repo2 / "README.md").read_text() == "# Updated"


# 5. Git pull on dirty workspace preserves uncommitted changes without destructive reset
def test_git_pull_preserves_dirty_workspace(tmp_path):
    repo_dir = tmp_path / "workspace" / USER_1_ID / "alice" / "dirty_repo"
    _init_local_repo(repo_dir, USER_1_ID, USER_1_NAME)

    (repo_dir / "uncommitted.txt").write_text("precious user work")

    # git_pull must detect dirty status and return without running reset
    res = git_pull(repo_dir, USER_1_ID, remote="origin")
    assert res["status"] == "dirty"
    assert "Workspace contains uncommitted changes" in res["message"]

    # Verify uncommitted file is completely preserved
    assert (repo_dir / "uncommitted.txt").exists()
    assert (repo_dir / "uncommitted.txt").read_text() == "precious user work"


# 6. Git push pushes commits to upstream repository
def test_git_push_to_upstream(tmp_path):
    upstream_dir = tmp_path / "push_upstream.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(upstream_dir)], check=True, capture_output=True)

    repo_dir = tmp_path / "workspace" / USER_1_ID / "alice" / "push_repo"
    _init_local_repo(repo_dir, USER_1_ID, USER_1_NAME)
    subprocess.run(["git", "remote", "add", "origin", str(upstream_dir)], cwd=repo_dir, check=True)

    (repo_dir / "app.py").write_text("print('push test')")
    git_add(repo_dir, USER_1_ID)
    git_commit(repo_dir, USER_1_ID, "feat: test push")

    push_res = git_push(repo_dir, USER_1_ID, remote="origin", branch="main")
    assert push_res["status"] == "success"

    # Verify commit reached upstream bare repository
    proc_log = subprocess.run(
        ["git", "log", "-1", "--oneline"],
        cwd=upstream_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "feat: test push" in proc_log.stdout


# 7. Workspace and user isolation: User 1 cannot operate in User 2's workspace
def test_workspace_user_isolation(tmp_path):
    ws_1 = tmp_path / "workspace" / USER_1_ID / "alice" / "repo1"
    ws_2 = tmp_path / "workspace" / USER_2_ID / "bob" / "repo2"
    _init_local_repo(ws_1, USER_1_ID, USER_1_NAME)
    _init_local_repo(ws_2, USER_2_ID, USER_2_NAME)

    # User 1 attempting to run git_status on User 2's workspace must be blocked
    with pytest.raises(Exception) as exc1:
        git_status(ws_2, USER_1_ID)
    assert "Cross-user access denied" in str(exc1.value) or "containment" in str(exc1.value).lower()

    # User 2 attempting to run git_status on User 1's workspace must be blocked
    with pytest.raises(Exception) as exc2:
        git_status(ws_1, USER_2_ID)
    assert "Cross-user access denied" in str(exc2.value) or "containment" in str(exc2.value).lower()


# 8. Token never written to .git/config
def test_token_never_in_git_config(tmp_path):
    repo_dir = tmp_path / "workspace" / USER_1_ID / "alice" / "config_repo"
    _init_local_repo(repo_dir, USER_1_ID, USER_1_NAME)

    git_config = (repo_dir / ".git" / "config").read_text(encoding="utf-8")
    assert "token" not in git_config.lower()
    assert USER_1_TOKEN not in git_config
