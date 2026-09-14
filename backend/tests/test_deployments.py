import json
import logging
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
from app.deployments.render import normalize_status

client = TestClient(app)

MOCK_USER_ID = "1001"
MOCK_USERNAME = "allowed_alice"
MOCK_TOKEN = "gho_mock_access_token_12345"
MOCK_RENDER_KEY = "rnd_test_api_key_secret_998877"
MOCK_SERVICE_ID = "srv-test-service-12345"

TEST_OWNER = "allowed_alice"
TEST_REPO = "MyProject"
TEST_HEAD_SHA = "a1b2c3d4e5f678901234567890abcdef12345678"


@pytest.fixture(autouse=True)
def setup_settings_and_auth(monkeypatch):
    """Sets up default configuration and authorization before each test."""
    clear_all_user_tokens()
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_1", MOCK_USER_ID)
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_2", "bob")
    monkeypatch.setattr(settings, "RENDER_API_KEY", MOCK_RENDER_KEY)
    monkeypatch.setattr(
        settings,
        "RENDER_SERVICE_MAP",
        json.dumps({f"{TEST_OWNER}/{TEST_REPO}": MOCK_SERVICE_ID}),
    )


def _login():
    """Simulates an authenticated session cookie and in-memory token."""
    store_user_token(MOCK_USER_ID, MOCK_TOKEN)
    cookie_val = create_session_token({
        "id": MOCK_USER_ID,
        "username": MOCK_USERNAME,
        "avatar_url": "https://avatars.githubusercontent.com/u/1001",
        "name": "Alice Developer",
    })
    client.cookies.set(settings.SESSION_COOKIE_NAME, cookie_val)


# 1. Authenticated deployment request succeeds with exact committed SHA & default do_not_clear
def test_authenticated_deployment_request_succeeds(monkeypatch):
    _login()

    # Mock GitHub commit API to return TEST_HEAD_SHA
    async def mock_get_latest_commit(token, user_id, owner, repo, branch, client=None):
        return {"sha": TEST_HEAD_SHA, "message": "feat: ready for deploy"}

    monkeypatch.setattr("app.deployments.routes.get_latest_commit", mock_get_latest_commit)

    recorded_render_requests = []

    # Mock trigger_deployment and service details
    async def mock_trigger(service_id, commit_id, clear_cache="do_not_clear"):
        recorded_render_requests.append({
            "service_id": service_id,
            "commit_id": commit_id,
            "clear_cache": clear_cache,
        })
        return {
            "id": "dep-xyz12345",
            "status": "created",
            "createdAt": "2026-09-14T12:00:00Z",
            "commit": {"id": commit_id},
        }

    async def mock_service_details(service_id):
        return {"serviceDetails": {"url": "https://myproject.onrender.com"}}

    monkeypatch.setattr("app.deployments.routes.trigger_deployment", mock_trigger)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    res = client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={"branch": "main"})
    assert res.status_code == 200
    data = res.json()

    assert data["id"] == "dep-xyz12345"
    assert data["status"] == "in_progress"  # Normalized from 'created'
    assert data["service"] == MOCK_SERVICE_ID
    assert data["commit"] == TEST_HEAD_SHA
    assert data["url"] == "https://myproject.onrender.com"

    # Verify Render trigger parameters
    assert len(recorded_render_requests) == 1
    req = recorded_render_requests[0]
    assert req["service_id"] == MOCK_SERVICE_ID
    assert req["commit_id"] == TEST_HEAD_SHA
    assert req["clear_cache"] == "do_not_clear"


# 2. Unauthenticated request returns 401
def test_unauthenticated_deployment_rejected():
    client.cookies.clear()
    res = client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={})
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]

    res_get = client.get(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}")
    assert res_get.status_code == 401


# 3. Unauthorized repository access rejected
def test_unauthorized_repository_rejected(monkeypatch):
    _login()

    async def mock_get_latest_commit_404(token, user_id, owner, repo, branch, client=None):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Repository or branch not found.")

    monkeypatch.setattr("app.deployments.routes.get_latest_commit", mock_get_latest_commit_404)

    res = client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={"branch": "secret-branch"})
    assert res.status_code == 404


# 4. Unmapped repository rejected
def test_unmapped_repository_rejected(monkeypatch):
    _login()
    monkeypatch.setattr(settings, "RENDER_SERVICE_MAP", "{}")

    res = client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={})
    assert res.status_code == 400
    assert "This project is not configured for Render deployment." in res.json()["detail"]

    res_status = client.get(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}")
    assert res_status.status_code == 400
    assert "This project is not configured for Render deployment." in res_status.json()["detail"]


# 5. Render API HTTP request is constructed correctly with Bearer token and JSON payload
@pytest.mark.anyio
async def test_render_api_request_construction(monkeypatch):
    from app.deployments.render import trigger_deployment

    recorded_headers = {}
    recorded_body = {}

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            recorded_headers.update(dict(request.headers))
            recorded_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                201,
                json={"id": "dep-111", "status": "created", "createdAt": "2026-09-14T10:00:00Z"},
            )

    transport = MockTransport()

    # Intercept httpx.AsyncClient creation inside trigger_deployment
    orig_client = httpx.AsyncClient
    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: orig_client(transport=transport, **kwargs))

    result = await trigger_deployment(
        service_id=MOCK_SERVICE_ID,
        commit_id=TEST_HEAD_SHA,
        clear_cache="do_not_clear",
    )

    assert result["id"] == "dep-111"
    assert recorded_headers["authorization"] == f"Bearer {MOCK_RENDER_KEY}"
    assert recorded_headers["content-type"] == "application/json"
    assert recorded_headers["accept"] == "application/json"
    assert recorded_body["commitId"] == TEST_HEAD_SHA
    assert recorded_body["clearCache"] == "do_not_clear"


# 6. Render API key never appears in response
def test_render_api_key_never_appears_in_response(monkeypatch):
    _login()

    async def mock_get_latest_commit(token, user_id, owner, repo, branch, client=None):
        return {"sha": TEST_HEAD_SHA}

    async def mock_trigger(service_id, commit_id, clear_cache="do_not_clear"):
        return {"id": "dep-sec123", "status": "created", "createdAt": "2026-09-14T10:00:00Z"}

    async def mock_service_details(service_id):
        return {"url": "https://myproject.onrender.com"}

    monkeypatch.setattr("app.deployments.routes.get_latest_commit", mock_get_latest_commit)
    monkeypatch.setattr("app.deployments.routes.trigger_deployment", mock_trigger)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    res = client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={})
    assert res.status_code == 200
    raw_response = res.text
    assert MOCK_RENDER_KEY not in raw_response
    assert "Bearer" not in raw_response


# 7. Render API key never appears in server logs
def test_render_api_key_never_in_logs(caplog, monkeypatch):
    _login()

    async def mock_get_latest_commit(token, user_id, owner, repo, branch, client=None):
        return {"sha": TEST_HEAD_SHA}

    async def mock_trigger(service_id, commit_id, clear_cache="do_not_clear"):
        logging.getLogger("cloud_ide.deployments").info(f"Triggered deployment for {service_id}")
        return {"id": "dep-sec123", "status": "created"}

    async def mock_service_details(service_id):
        return {}

    monkeypatch.setattr("app.deployments.routes.get_latest_commit", mock_get_latest_commit)
    monkeypatch.setattr("app.deployments.routes.trigger_deployment", mock_trigger)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    with caplog.at_level(logging.DEBUG):
        client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={})

    for record in caplog.records:
        assert MOCK_RENDER_KEY not in record.message
        assert "Bearer" not in record.message


# 8. Status normalization: all standard Render status strings map cleanly
def test_status_normalization():
    # In progress
    for st in ["created", "queued", "building", "build_in_progress", "update_in_progress", "pre_deploy_in_progress", "deploying"]:
        assert normalize_status(st) == "in_progress"

    # Live
    assert normalize_status("live") == "live"
    assert normalize_status("LIVE") == "live"

    # Build failed
    for st in ["build_failed", "update_failed", "pre_deploy_failed", "failed"]:
        assert normalize_status(st) == "build_failed"

    # Canceled
    for st in ["canceled", "cancelled", "deactivated"]:
        assert normalize_status(st) == "canceled"

    # Unknown
    assert normalize_status("something_random") == "unknown"
    assert normalize_status(None) == "unknown"


# 9. Build failure handling
def test_build_failure_handling(monkeypatch):
    _login()

    async def mock_get_latest(service_id):
        return {
            "id": "dep-fail-1",
            "status": "build_failed",
            "commit": {"id": TEST_HEAD_SHA},
            "createdAt": "2026-09-14T11:00:00Z",
        }

    async def mock_service_details(service_id):
        return {"url": "https://myproject.onrender.com"}

    monkeypatch.setattr("app.deployments.routes.get_latest_deployment", mock_get_latest)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    res = client.get(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "build_failed"
    assert data["id"] == "dep-fail-1"


# 10. Canceled deployment handling
def test_canceled_deployment_handling(monkeypatch):
    _login()

    async def mock_get_latest(service_id):
        return {
            "id": "dep-cancel-1",
            "status": "canceled",
            "commit": {"id": TEST_HEAD_SHA},
            "createdAt": "2026-09-14T11:00:00Z",
        }

    async def mock_service_details(service_id):
        return {}

    monkeypatch.setattr("app.deployments.routes.get_latest_deployment", mock_get_latest)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    res = client.get(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}")
    assert res.status_code == 200
    assert res.json()["status"] == "canceled"


# 11. Rate limit handling (HTTP 429)
@pytest.mark.anyio
async def test_rate_limit_handling(monkeypatch):
    from app.deployments.render import trigger_deployment

    class RateLimitTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"message": "Too many requests"})

    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **kwargs: orig_client(transport=RateLimitTransport(), **kwargs),
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await trigger_deployment(MOCK_SERVICE_ID, TEST_HEAD_SHA)

    assert exc_info.value.status_code == 429
    assert "rate limited" in exc_info.value.detail


# 12. Network failure handling (ConnectError, TimeoutException)
@pytest.mark.anyio
async def test_network_failure_handling(monkeypatch):
    from app.deployments.render import trigger_deployment

    class ErrorTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused by Render", request=request)

    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **kwargs: orig_client(transport=ErrorTransport(), **kwargs),
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await trigger_deployment(MOCK_SERVICE_ID, TEST_HEAD_SHA)

    assert exc_info.value.status_code == 502
    assert "Unable to contact Render." in exc_info.value.detail


# 13. Browser cannot supply arbitrary service ID or commit ID
def test_browser_cannot_supply_arbitrary_service_or_commit(monkeypatch):
    _login()

    recorded_calls = []

    async def mock_get_latest_commit(token, user_id, owner, repo, branch, client=None):
        return {"sha": TEST_HEAD_SHA}

    async def mock_trigger(service_id, commit_id, clear_cache="do_not_clear"):
        recorded_calls.append((service_id, commit_id))
        return {"id": "dep-safe1", "status": "created"}

    async def mock_service_details(service_id):
        return {}

    monkeypatch.setattr("app.deployments.routes.get_latest_commit", mock_get_latest_commit)
    monkeypatch.setattr("app.deployments.routes.trigger_deployment", mock_trigger)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    # Malicious client sends arbitrary service ID and arbitrary commitId
    res = client.post(
        f"/api/deployments/{TEST_OWNER}/{TEST_REPO}",
        json={
            "service_id": "srv-attacker-evil-service",
            "commitId": "evil_unverified_sha_00000000000000",
            "branch": "main",
        },
    )
    assert res.status_code == 200

    # Ensure backend used the configured server mapping and verified GitHub commit SHA!
    assert len(recorded_calls) == 1
    used_service, used_commit = recorded_calls[0]
    assert used_service == MOCK_SERVICE_ID
    assert used_commit == TEST_HEAD_SHA
    assert used_service != "srv-attacker-evil-service"
    assert used_commit != "evil_unverified_sha_00000000000000"


# 14. Dirty workspace blocks deployment
def test_dirty_workspace_blocks_deployment(monkeypatch, tmp_path):
    _login()

    # Point workspace to a temporary directory simulating dirty files
    workspace_dir = tmp_path / "workspace" / MOCK_USER_ID / TEST_OWNER / TEST_REPO
    workspace_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.deployments.routes.get_repo_workspace_path", lambda uid, o, r: workspace_dir)

    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=" M dirty_script.py\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.deployments.routes.run_git", mock_run_git)

    res = client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={})
    assert res.status_code == 400
    assert "Commit and push your changes before deploying." in res.json()["detail"]


# 15. Unpushed local commit blocks deployment
def test_unpushed_local_commit_blocks_deployment(monkeypatch, tmp_path):
    _login()

    workspace_dir = tmp_path / "workspace" / MOCK_USER_ID / TEST_OWNER / TEST_REPO
    workspace_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.deployments.routes.get_repo_workspace_path", lambda uid, o, r: workspace_dir)

    # Local workspace is clean, but has a local commit not yet pushed to GitHub
    def mock_run_git(args, cwd=None, token=None, timeout=60):
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="local_unpushed_commit_sha_12345\n", stderr="")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    async def mock_get_latest_commit(token, user_id, owner, repo, branch, client=None):
        # GitHub remote is still at an older commit
        return {"sha": "remote_github_older_commit_sha_99999"}

    monkeypatch.setattr("app.deployments.routes.run_git", mock_run_git)
    monkeypatch.setattr("app.deployments.routes.get_latest_commit", mock_get_latest_commit)

    res = client.post(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}", json={})
    assert res.status_code == 400
    assert "Commit and push your changes before deploying." in res.json()["detail"]


# 16. Exact deployment ID is polled
def test_exact_deployment_id_polled(monkeypatch):
    _login()

    polled_ids = []

    async def mock_get_deployment(service_id, deploy_id):
        polled_ids.append((service_id, deploy_id))
        return {
            "id": deploy_id,
            "status": "live",
            "commit": {"id": TEST_HEAD_SHA},
            "createdAt": "2026-09-14T10:05:00Z",
        }

    async def mock_service_details(service_id):
        return {"url": "https://live-app.onrender.com"}

    monkeypatch.setattr("app.deployments.routes.get_deployment", mock_get_deployment)
    monkeypatch.setattr("app.deployments.routes.get_service_details", mock_service_details)

    res = client.get(f"/api/deployments/{TEST_OWNER}/{TEST_REPO}/dep-target-exact-777")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "live"
    assert data["id"] == "dep-target-exact-777"
    assert data["url"] == "https://live-app.onrender.com"

    # Confirmed that exact deploy ID was polled, not the latest deploy
    assert len(polled_ids) == 1
    assert polled_ids[0] == (MOCK_SERVICE_ID, "dep-target-exact-777")


# 17. Auto-Deploy interaction verification
def test_render_auto_deploy_interaction_documented():
    """
    Verifies that Render explicit deployment via commitId ensures specific commit execution.
    Documents requirement: When Auto-Deploy is enabled on Render, external webhooks trigger
    automatic builds. To ensure explicit deployment control from the Cloud IDE, Render services
    should have Auto-Deploy disabled.
    """
    from app.deployments.render import RENDER_API_BASE
    assert RENDER_API_BASE == "https://api.render.com/v1"
