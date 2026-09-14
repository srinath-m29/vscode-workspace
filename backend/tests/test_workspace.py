import os
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import httpx

from app.main import app
from app.config import settings
from app.auth.session import (
    create_session_token,
    store_user_token,
    clear_all_user_tokens,
)
from app.github.client import clear_all_github_cache
from app.projects.manager import (
    get_user_workspace_root,
    get_repo_workspace_path,
    validate_branch_name,
    run_git,
)

client = TestClient(app)

USER_1_ID = "1001"
USER_1_NAME = "allowed_alice"
USER_1_TOKEN = "gho_mock_token_alice_11111"

USER_2_ID = "99999"
USER_2_NAME = "allowed_bob"
USER_2_TOKEN = "gho_mock_token_bob_22222"


@pytest.fixture(autouse=True)
def setup_environment(monkeypatch, tmp_path):
    """Isolate workspace root to temporary test directory and reset auth/cache."""
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_dir))
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_1", USER_1_NAME)
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_2", USER_2_ID)
    clear_all_user_tokens()
    clear_all_github_cache()


def _login(user_id: str, username: str, token: str):
    """Logs in specified user and stores in-memory token."""
    user = {"id": user_id, "username": username}
    session_token = create_session_token(user)
    store_user_token(user_id, token)
    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)


def _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main"):
    """Mocks GitHub API checks for repository metadata and branch existence."""
    async def mock_api_request(endpoint, token, user_id, params=None, client=None, use_cache=True):
        clean = endpoint.lstrip("/")
        if clean == f"repos/{valid_owner}/{valid_repo}":
            return {
                "id": 123,
                "name": valid_repo,
                "full_name": f"{valid_owner}/{valid_repo}",
                "default_branch": valid_branch,
            }
        elif clean.startswith(f"repos/{valid_owner}/{valid_repo}/branches/"):
            req_branch = clean.split(f"repos/{valid_owner}/{valid_repo}/branches/")[1]
            if req_branch == valid_branch or req_branch in ("main", "feature/login", "dev/backend"):
                return {"name": req_branch, "commit": {"sha": "abcdef123456"}}
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Branch not found")
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Repository not found")

    monkeypatch.setattr("app.projects.manager.github_api_request", mock_api_request)


# 1. Unauthenticated request returns 401.
def test_unauthenticated_request_rejected():
    client.cookies.clear()
    res = client.post("/api/projects/open", json={"owner": "alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 401


# 2. Workspace path is scoped by authenticated numeric GitHub ID.
def test_workspace_path_scoped_by_user_id():
    user_root = get_user_workspace_root(USER_1_ID)
    assert user_root.name == USER_1_ID

    repo_path = get_repo_workspace_path(USER_1_ID, "alice", "QPapers")
    assert repo_path.parts[-3] == USER_1_ID
    assert repo_path.parts[-2] == "alice"
    assert repo_path.parts[-1] == "QPapers"


# 3. User 1 and User 2 using repositories with the same name do not collide.
def test_user_isolation_same_repo_name():
    p1 = get_repo_workspace_path(USER_1_ID, "org", "same-repo")
    p2 = get_repo_workspace_path(USER_2_ID, "org", "same-repo")

    assert p1 != p2
    assert USER_1_ID in str(p1)
    assert USER_2_ID in str(p2)
    assert USER_1_ID not in str(p2)
    assert USER_2_ID not in str(p1)


# 4. Branch names containing '/' are accepted.
def test_branch_with_slash_accepted():
    validate_branch_name("feature/login")
    validate_branch_name("dev/backend/auth")
    validate_branch_name("release/v1.0")


# 5. Malicious branch refs are rejected.
def test_malicious_branch_refs_rejected():
    with pytest.raises(Exception):
        validate_branch_name("../etc/passwd")

    with pytest.raises(Exception):
        validate_branch_name("-f")

    with pytest.raises(Exception):
        validate_branch_name("bad\0name")

    with pytest.raises(Exception):
        validate_branch_name("/leading/slash")

    with pytest.raises(Exception):
        validate_branch_name("trailing/slash/")

    with pytest.raises(Exception):
        validate_branch_name("bad@{ref}")


# 6. Invalid owner and repository names rejected (traversal, slashes, null bytes).
def test_invalid_owner_and_repo_rejected():
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)

    # Traversal in repo
    res1 = client.post("/api/projects/open", json={"owner": "alice", "repo": "../etc", "branch": "main"})
    assert res1.status_code == 400

    # Slashes in repo name
    res2 = client.post("/api/projects/open", json={"owner": "alice", "repo": "sub/repo", "branch": "main"})
    assert res2.status_code == 400

    # Shell injection in repo name
    res3 = client.post("/api/projects/open", json={"owner": "alice", "repo": "repo;rm -rf", "branch": "main"})
    assert res3.status_code == 400

    # Traversal in owner
    res4 = client.post("/api/projects/open", json={"owner": "..", "repo": "QPapers", "branch": "main"})
    assert res4.status_code == 400


# 7. Missing/inaccessible repository rejected with 404.
def test_missing_repository_rejected(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    res = client.post("/api/projects/open", json={"owner": "other_user", "repo": "secret-repo", "branch": "main"})
    assert res.status_code == 404
    assert "Repository not found or inaccessible" in res.json()["detail"]


# 8. Missing branch rejected with 404.
def test_missing_branch_rejected(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "nonexistent_branch"})
    assert res.status_code == 404
    assert "Branch 'nonexistent_branch' not found" in res.json()["detail"]


# 9. Initial clone creates workspace using mock git command.
def test_successful_initial_clone(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    # Mock run_git to simulate successful git clone
    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args[0] == "clone":
            target_dir = Path(args[4])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / ".git").mkdir(parents=True, exist_ok=True)
            (target_dir / "README.md").write_text("# QPapers")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["owner"] == "allowed_alice"
    assert data["repo"] == "QPapers"
    assert data["branch"] == "main"
    assert USER_1_ID in data["workspace"]
    # Step 9 open_url assertions
    assert data["open_url"] is not None
    assert data["open_url"].startswith("/vscode/?folder=")
    assert "%2F" in data["open_url"]
    assert USER_1_ID in data["open_url"]


# 10. Existing clean workspace is reused and updated.
def test_existing_clean_workspace_reused(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    target_path = get_repo_workspace_path(USER_1_ID, "allowed_alice", "QPapers")
    target_path.mkdir(parents=True, exist_ok=True)
    (target_path / ".git").mkdir(parents=True, exist_ok=True)

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args == ["config", "--get", "remote.origin.url"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/allowed_alice/QPapers.git\n", stderr="")
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["open_url"] is not None
    assert data["open_url"].startswith("/vscode/?folder=")


# 11. Existing dirty workspace is detected and NOT modified.
def test_existing_dirty_workspace_detected_and_preserved(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    target_path = get_repo_workspace_path(USER_1_ID, "allowed_alice", "QPapers")
    target_path.mkdir(parents=True, exist_ok=True)
    (target_path / ".git").mkdir(parents=True, exist_ok=True)

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args == ["config", "--get", "remote.origin.url"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/allowed_alice/QPapers.git\n", stderr="")
        if args == ["status", "--porcelain"]:
            # Dirty working tree: modified file and untracked file
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=" M app.py\n?? test.txt\n", stderr="")
        # If reset, clean, or checkout is called on dirty tree, fail test!
        if "reset" in args or "clean" in args:
            pytest.fail("Git reset or clean must NEVER be executed on dirty workspace!")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "dirty"
    assert "uncommitted changes" in data["message"]
    # Step 9 dirty workspace rule: open_url must be None!
    assert data["open_url"] is None


# 12. Existing workspace with origin pointing to another repository is rejected.
def test_existing_workspace_origin_mismatch_rejected(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    target_path = get_repo_workspace_path(USER_1_ID, "allowed_alice", "QPapers")
    target_path.mkdir(parents=True, exist_ok=True)
    (target_path / ".git").mkdir(parents=True, exist_ok=True)

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args == ["config", "--get", "remote.origin.url"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/attacker/malicious-repo.git\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 400
    assert "belongs to a different repository" in res.json()["detail"]


# 13. Token never appears in git remote URL or command arguments.
def test_token_never_in_git_remote_or_args(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    recorded_args = []

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        recorded_args.append((args, token))
        if args[0] == "clone":
            target_dir = Path(args[4])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / ".git").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 200

    # Ensure recorded command arguments contain NO token
    for cmd_args, token_passed in recorded_args:
        for arg in cmd_args:
            assert USER_1_TOKEN not in arg
            assert "x-access-token" not in arg
    # Ensure remote URL is clean in clone command
    assert any("https://github.com/allowed_alice/QPapers.git" in cmd for cmd, _ in recorded_args)


# 14. Ephemeral GIT_ASKPASS helper functionality.
def test_git_askpass_helper(monkeypatch):
    from app.projects.askpass import main as askpass_main

    # Test Username prompt
    monkeypatch.setattr("sys.argv", ["askpass.py", "Username for 'https://github.com':"])
    import io, sys
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    askpass_main()
    assert out.getvalue().strip() == "x-access-token"

    # Test Password prompt
    monkeypatch.setenv("_CLOUDIDE_GIT_TOKEN", "mock_ephemeral_token_secret")
    monkeypatch.setattr("sys.argv", ["askpass.py", "Password for 'https://github.com':"])
    out2 = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out2)
    askpass_main()
    assert out2.getvalue().strip() == "mock_ephemeral_token_secret"


# 15. Symlink escape is rejected.
def test_symlink_escape_rejected(monkeypatch, tmp_path):
    outside_dir = tmp_path / "outside_secret_area"
    outside_dir.mkdir(parents=True, exist_ok=True)

    user_root = get_user_workspace_root(USER_1_ID)
    user_root.mkdir(parents=True, exist_ok=True)

    target_parent = user_root / "allowed_alice"
    target_parent.mkdir(parents=True, exist_ok=True)
    symlink_path = target_parent / "QPapers"

    # Create symlink pointing outside user_root
    try:
        os.symlink(outside_dir, symlink_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        # On Windows without developer mode/admin symlinks may require skip
        pytest.skip("Symlink creation not permitted on this host OS.")

    with pytest.raises(Exception) as exc_info:
        get_repo_workspace_path(USER_1_ID, "allowed_alice", "QPapers")
    assert "Symlink" in str(exc_info.value.detail) or "containment" in str(exc_info.value.detail)


# 16. User 1 cannot access User 2's workspace directory via API.
def test_cross_user_workspace_access_blocked(monkeypatch):
    # User 2 creates a workspace
    _login(USER_2_ID, USER_2_NAME, USER_2_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="bob", valid_repo="PrivateProject", valid_branch="main")

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args[0] == "clone":
            target_dir = Path(args[4])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / ".git").mkdir(parents=True, exist_ok=True)
            (target_dir / "secret.txt").write_text("Bob's secret file")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res2 = client.post("/api/projects/open", json={"owner": "bob", "repo": "PrivateProject", "branch": "main"})
    assert res2.status_code == 200
    bob_workspace = res2.json()["workspace"]
    assert USER_2_ID in bob_workspace

    # User 1 logs in and requests the same repository
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="bob", valid_repo="PrivateProject", valid_branch="main")

    res1 = client.post("/api/projects/open", json={"owner": "bob", "repo": "PrivateProject", "branch": "main"})
    assert res1.status_code == 200
    alice_workspace = res1.json()["workspace"]

    # User 1's workspace must be strictly inside User 1's directory, NOT Bob's
    assert USER_1_ID in alice_workspace
    assert bob_workspace != alice_workspace
    assert not Path(alice_workspace).is_relative_to(get_user_workspace_root(USER_2_ID))


# 17. Token never appears in .git/config on disk.
def test_token_never_written_to_git_config(monkeypatch, tmp_path):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    target_path = get_repo_workspace_path(USER_1_ID, "allowed_alice", "QPapers")
    target_path.mkdir(parents=True, exist_ok=True)
    git_dir = target_path / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    git_config_file = git_dir / "config"
    git_config_file.write_text("[remote \"origin\"]\n\turl = https://github.com/allowed_alice/QPapers.git\n")

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args == ["config", "--get", "remote.origin.url"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/allowed_alice/QPapers.git\n", stderr="")
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 200

    config_content = git_config_file.read_text()
    assert USER_1_TOKEN not in config_content
    assert "token" not in config_content.lower()


# 18. Step 9: open_url encoding and user isolation validation.
def test_open_url_format_and_user_isolation(monkeypatch):
    import urllib.parse

    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    _mock_github_repo_and_branch_api(monkeypatch, valid_owner="allowed_alice", valid_repo="QPapers", valid_branch="main")

    target_path = get_repo_workspace_path(USER_1_ID, "allowed_alice", "QPapers")
    target_path.mkdir(parents=True, exist_ok=True)
    (target_path / ".git").mkdir(parents=True, exist_ok=True)

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args == ["config", "--get", "remote.origin.url"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/allowed_alice/QPapers.git\n", stderr="")
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.projects.manager.run_git", mock_run_git)

    res = client.post("/api/projects/open", json={"owner": "allowed_alice", "repo": "QPapers", "branch": "main"})
    assert res.status_code == 200
    data = res.json()

    # Verify complete encoding of path (safe="")
    expected_encoded = urllib.parse.quote(target_path.resolve().as_posix(), safe="")
    assert data["open_url"] == f"/vscode/?folder={expected_encoded}"
    assert USER_1_ID in data["open_url"]
    assert USER_2_ID not in data["open_url"]


# 19. Step 9: Verify urllib.parse.quote(str(workspace_path), safe="") matches example.
def test_open_url_example_path_encoding():
    import urllib.parse
    example_path = Path("/home/workspace/123456/owner/QPapers")
    encoded = urllib.parse.quote(str(example_path.as_posix()), safe="")
    assert encoded == "%2Fhome%2Fworkspace%2F123456%2Fowner%2FQPapers"
    assert f"/vscode/?folder={encoded}" == "/vscode/?folder=%2Fhome%2Fworkspace%2F123456%2Fowner%2FQPapers"

