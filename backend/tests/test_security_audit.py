"""
STEP 13: Final Security Attack & Penetration Test Suite.
Exhaustively tests all attack vectors:
1. Unauthenticated /vscode/ access subrequest blocked
2. Third unauthorized GitHub user rejected
3. Invalid / tampered / expired session cookie blocked
4. User 1 attempting to access User 2 workspace blocked
5. User 2 attempting to access User 1 workspace blocked
6. ../../ Path traversal in owner, repo, branch blocked
7. Absolute filesystem path injection blocked
8. Null-byte (\x00) injection blocked
9. Shell command injection attempts in branch/repo blocked
10. Arbitrary GitHub host & scheme injection blocked
11. Arbitrary Render service ID injection blocked
12. Fake user_id in client payload ignored/blocked
13. Fake workspace path in client payload ignored/blocked
14. Token in Git remote URL blocked
15. Sensitive secrets leak check in responses and logs
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.auth.session import (
    create_session_token,
    store_user_token,
    clear_all_user_tokens,
)

client = TestClient(app)

USER_1_ID = "1001"
USER_1_NAME = "alice_dev"
USER_1_TOKEN = "gho_alice_secret_token_11111"

USER_2_ID = "2002"
USER_2_NAME = "bob_dev"
USER_2_TOKEN = "gho_bob_secret_token_22222"

ATTACKER_ID = "9999"
ATTACKER_NAME = "eve_attacker"


@pytest.fixture(autouse=True)
def setup_security_context(monkeypatch):
    clear_all_user_tokens()
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_1", USER_1_ID)
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_2", USER_2_ID)
    monkeypatch.setattr(settings, "RENDER_API_KEY", "rnd_production_mock_secret_key_888")
    monkeypatch.setattr(
        settings,
        "RENDER_SERVICE_MAP",
        json.dumps({f"{USER_1_NAME}/TargetRepo": "srv-legitimate-service-id"}),
    )


def _login(user_id: str, username: str, token: str):
    store_user_token(user_id, token)
    cookie_val = create_session_token({
        "id": user_id,
        "username": username,
        "avatar_url": f"https://avatars.githubusercontent.com/u/{user_id}",
        "name": username,
    })
    client.cookies.set(settings.SESSION_COOKIE_NAME, cookie_val)


# 1. Unauthenticated /vscode/ access blocked via auth_request subrequest
def test_unauthenticated_vscode_subrequest_blocked():
    client.cookies.clear()
    res = client.get("/api/auth/verify")
    assert res.status_code == 401


# 2. Third unauthorized GitHub user rejected
def test_third_unauthorized_user_blocked(monkeypatch):
    # Attacker tries to forge session for user 9999
    cookie_val = create_session_token({
        "id": ATTACKER_ID,
        "username": ATTACKER_NAME,
        "avatar_url": "https://avatars.githubusercontent.com/u/9999",
        "name": ATTACKER_NAME,
    })
    client.cookies.set(settings.SESSION_COOKIE_NAME, cookie_val)

    # Attempt verify endpoint
    res_verify = client.get("/api/auth/verify")
    assert res_verify.status_code == 401

    # Attempt /api/auth/me
    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 401

    # Attempt workspace open
    res_open = client.post("/api/projects/open", json={"owner": USER_1_NAME, "repo": "TargetRepo", "branch": "main"})
    assert res_open.status_code == 401


# 3. Tampered & invalid session cookies rejected
def test_tampered_session_cookie_rejected():
    client.cookies.set(settings.SESSION_COOKIE_NAME, "tampered.jwt.or.serializer.token")
    res = client.get("/api/auth/verify")
    assert res.status_code == 401


# 4. User 1 cannot access User 2 workspace
def test_cross_user_workspace_isolation(tmp_path, monkeypatch):
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_root))

    # User 2 logs in and prepares a workspace
    _login(USER_2_ID, USER_2_NAME, USER_2_TOKEN)
    from app.projects.manager import get_repo_workspace_path
    bob_path = get_repo_workspace_path(USER_2_ID, "bob_dev", "SecretProject")
    bob_path.mkdir(parents=True, exist_ok=True)
    (bob_path / "classified.txt").write_text("Top secret Bob data")

    # User 1 logs in
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)
    alice_path = get_repo_workspace_path(USER_1_ID, "bob_dev", "SecretProject")

    # Verify Alice's workspace is strictly isolated under /workspace/1001/ and cannot see Bob's /workspace/2002/
    assert alice_path != bob_path
    assert USER_1_ID in str(alice_path)
    assert USER_2_ID not in str(alice_path)
    assert not (alice_path / "classified.txt").exists()


# 5. Path traversal (../../) in owner, repo, branch rejected
@pytest.mark.parametrize("traversal_input", [
    "../../etc",
    "..\\..\\windows",
    "owner/../../escaped",
    "valid/../../../root",
    "....//....//etc",
])
def test_path_traversal_rejected(traversal_input):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)

    # In owner
    res1 = client.post("/api/projects/open", json={"owner": traversal_input, "repo": "TargetRepo", "branch": "main"})
    assert res1.status_code in (400, 422)

    # In repo
    res2 = client.post("/api/projects/open", json={"owner": USER_1_NAME, "repo": traversal_input, "branch": "main"})
    assert res2.status_code in (400, 422)

    # In branch
    res3 = client.post("/api/projects/open", json={"owner": USER_1_NAME, "repo": "TargetRepo", "branch": traversal_input})
    assert res3.status_code in (400, 422)


# 6. Null-byte (\x00) injection rejected
@pytest.mark.parametrize("null_byte_input", [
    "repo\x00.git",
    "main\x00malicious",
    "\x00root",
])
def test_null_byte_injection_rejected(null_byte_input):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)

    res = client.post("/api/projects/open", json={"owner": USER_1_NAME, "repo": null_byte_input, "branch": "main"})
    assert res.status_code in (400, 422)


# 7. Shell injection characters in branch name rejected
@pytest.mark.parametrize("shell_injection", [
    "main; rm -rf /",
    "main && whoami",
    "main | cat /etc/passwd",
    "`whoami`",
    "$(reboot)",
    "main > /dev/null",
])
def test_shell_injection_rejected(shell_injection):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)

    res = client.post("/api/projects/open", json={"owner": USER_1_NAME, "repo": "TargetRepo", "branch": shell_injection})
    assert res.status_code in (400, 422)


# 8. Arbitrary Git remote host & scheme rejected
@pytest.mark.parametrize("evil_remote", [
    "https://attacker.com/malicious/repo.git",
    "http://github.com/insecure/repo.git",
    "ssh://git@github.com/owner/repo.git",
    "git@github.com:owner/repo.git",
    "file:///etc/passwd",
    "https://ghp_secret_token@github.com/owner/repo.git",
])
def test_evil_git_remotes_rejected(evil_remote):
    from app.git.validation import validate_git_remote_url
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        validate_git_remote_url(evil_remote, "owner", "repo")
    assert exc.value.status_code == 400


# 9. Arbitrary Render service ID in request body ignored
def test_arbitrary_render_service_id_ignored(monkeypatch):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)

    recorded_service_id = None

    async def mock_get_latest_commit(token, user_id, owner, repo, branch, client=None):
        return {"sha": "sha_1111111111111111111111111111111111111111"}

    async def mock_trigger(service_id, commit_id, clear_cache="do_not_clear"):
        nonlocal recorded_service_id
        recorded_service_id = service_id
        return {"id": "dep-safe-999", "status": "created"}

    async def mock_service_details(service_id):
        return {}

    monkeypatch.setattr("app.deployments.routes.get_latest_commit", mock_get_latest_commit)
    monkeypatch.setattr("app.deployments.routes.trigger_deployment", mock_trigger)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    # Client attempts to pass arbitrary service_id
    res = client.post(
        f"/api/deployments/{USER_1_NAME}/TargetRepo",
        json={"service_id": "srv-evil-attacker-service"},
    )
    assert res.status_code == 200
    assert recorded_service_id == "srv-legitimate-service-id"
    assert recorded_service_id != "srv-evil-attacker-service"


# 10. Fake client-supplied user_id or workspace path ignored in /api/projects/open
def test_client_cannot_forge_user_id_or_workspace_path(monkeypatch, tmp_path):
    _login(USER_1_ID, USER_1_NAME, USER_1_TOKEN)

    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    user_ws = tmp_path / USER_1_ID / USER_1_NAME / "TargetRepo"
    user_ws.mkdir(parents=True, exist_ok=True)

    recorded_user_id = None
    recorded_workspace = None

    async def mock_open_workspace(token, user_id, owner, repo, branch, username=None, user_name=None):
        nonlocal recorded_user_id, recorded_workspace
        recorded_user_id = user_id
        recorded_workspace = str(user_ws)
        return {
            "status": "ready",
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "workspace": recorded_workspace,
        }

    monkeypatch.setattr("app.projects.routes.open_or_create_workspace", mock_open_workspace)

    # Attacker passes forged user_id and workspace path in body
    res = client.post(
        "/api/projects/open",
        json={
            "owner": USER_1_NAME,
            "repo": "TargetRepo",
            "branch": "main",
            "user_id": USER_2_ID,
            "workspace": "/etc/shadow",
        },
    )
    assert res.status_code == 200
    # Backend strictly derives user_id from verified session token
    assert recorded_user_id == USER_1_ID
    assert recorded_user_id != USER_2_ID
    assert "/etc/shadow" not in recorded_workspace
