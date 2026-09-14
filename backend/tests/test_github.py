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

client = TestClient(app)

MOCK_USER_ID = "1001"
MOCK_USERNAME = "allowed_alice"
MOCK_TOKEN = "gho_secret_access_token_mock_12345"

SAMPLE_RAW_REPOS = [
    {
        "id": 101,
        "name": "RepoOne",
        "full_name": "allowed_alice/RepoOne",
        "description": "First test repository",
        "private": True,
        "default_branch": "main",
        "html_url": "https://github.com/allowed_alice/RepoOne",
        "language": "Python",
        "updated_at": "2026-09-14T10:00:00Z",
        "owner": {"login": "allowed_alice"},
        "node_id": "secret_internal_node_id_1",
    },
    {
        "id": 102,
        "name": "WebFrontend",
        "full_name": "allowed_alice/WebFrontend",
        "description": "React TypeScript UI portal",
        "private": False,
        "default_branch": "dev",
        "html_url": "https://github.com/allowed_alice/WebFrontend",
        "language": "TypeScript",
        "updated_at": "2026-09-13T12:00:00Z",
        "owner": {"login": "allowed_alice"},
        "node_id": "secret_internal_node_id_2",
    },
]

SAMPLE_RAW_BRANCHES = [
    {"name": "main", "commit": {"sha": "abc111"}},
    {"name": "feature-auth", "commit": {"sha": "abc222"}},
]

SAMPLE_RAW_COMMIT = [
    {
        "sha": "1234567890abcdef1234567890abcdef12345678",
        "commit": {
            "message": "feat: integrate GitHub repository listing\n\nDetailed commit message",
            "author": {"name": "Alice Developer", "date": "2026-09-14T09:30:00Z"},
            "committer": {"name": "Alice Developer", "date": "2026-09-14T09:30:00Z"},
        },
        "author": {"login": "allowed_alice"},
    }
]


@pytest.fixture(autouse=True)
def setup_test_auth(monkeypatch):
    """Set up two-user allowlist, clear in-memory tokens and GitHub cache."""
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_1", MOCK_USERNAME)
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_2", "99999")
    clear_all_user_tokens()
    clear_all_github_cache()


def _login_test_user():
    """Helper to authenticate the test user and store an in-memory token."""
    user = {"id": MOCK_USER_ID, "username": MOCK_USERNAME}
    session_token = create_session_token(user)
    store_user_token(MOCK_USER_ID, MOCK_TOKEN)
    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)


# 1. Authenticated repository list succeeds.
def test_authenticated_repository_list_success(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json=SAMPLE_RAW_REPOS,
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories")
    assert res.status_code == 200
    data = res.json()
    assert "repositories" in data
    assert len(data["repositories"]) == 2
    assert data["repositories"][0]["name"] == "RepoOne"


# 2. Unauthenticated repository list returns 401.
def test_unauthenticated_repository_list_rejected():
    client.cookies.clear()
    res = client.get("/api/github/repositories")
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]


# 3. Repository list is normalized correctly.
def test_repository_normalization(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json=[SAMPLE_RAW_REPOS[0]],
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories")
    assert res.status_code == 200
    repo = res.json()["repositories"][0]

    # Verify expected normalized fields exist
    assert repo["id"] == 101
    assert repo["name"] == "RepoOne"
    assert repo["full_name"] == "allowed_alice/RepoOne"
    assert repo["description"] == "First test repository"
    assert repo["private"] is True
    assert repo["default_branch"] == "main"
    assert repo["html_url"] == "https://github.com/allowed_alice/RepoOne"
    assert repo["language"] == "Python"
    assert repo["updated_at"] == "2026-09-14T10:00:00Z"
    assert repo["owner"] == "allowed_alice"

    # Verify raw internal fields are stripped
    assert "node_id" not in repo


# 4. Pagination works.
def test_repository_pagination(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        params = kwargs.get("params", {})
        assert params.get("page") == 2
        assert params.get("per_page") == 10
        return httpx.Response(
            status_code=200,
            json=[SAMPLE_RAW_REPOS[1]],
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories?page=2&per_page=10")
    assert res.status_code == 200
    data = res.json()
    assert data["page"] == 2
    assert data["per_page"] == 10
    assert len(data["repositories"]) == 1


# 5. Search works.
def test_repository_search_filter(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json=SAMPLE_RAW_REPOS,
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # Search by name substring
    res = client.get("/api/github/repositories?search=Frontend")
    assert res.status_code == 200
    data = res.json()
    assert len(data["repositories"]) == 1
    assert data["repositories"][0]["name"] == "WebFrontend"

    # Search by description substring
    res_desc = client.get("/api/github/repositories?search=portal")
    assert res_desc.status_code == 200
    assert len(res_desc.json()["repositories"]) == 1


# 6. Branch listing succeeds and identifies default branch.
def test_branch_listing_identifies_default(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        url_str = str(url)
        if url_str.endswith("/branches"):
            return httpx.Response(
                status_code=200,
                json=SAMPLE_RAW_BRANCHES,
                request=httpx.Request("GET", url_str),
            )
        else:
            # Metadata endpoint to determine default branch
            return httpx.Response(
                status_code=200,
                json={"default_branch": "main"},
                request=httpx.Request("GET", url_str),
            )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories/allowed_alice/RepoOne/branches")
    assert res.status_code == 200
    data = res.json()
    assert "branches" in data
    branches = data["branches"]
    assert len(branches) == 2

    # Verify default branch marked
    main_b = next(b for b in branches if b["name"] == "main")
    assert main_b["default"] is True

    feat_b = next(b for b in branches if b["name"] == "feature-auth")
    assert feat_b["default"] is False


# 7. Unauthorized repository access is rejected.
def test_unauthorized_repository_rejected(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=404,
            json={"message": "Not Found"},
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories/other_user/private_repo/branches")
    assert res.status_code == 404
    assert res.json()["detail"] == "Unable to access this repository."


# 8. Latest commit retrieval succeeds.
def test_latest_commit_retrieval(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json=SAMPLE_RAW_COMMIT,
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories/allowed_alice/RepoOne/commits/latest?branch=main")
    assert res.status_code == 200
    data = res.json()
    assert data["sha"] == "1234567890abcdef1234567890abcdef12345678"
    assert data["message"] == "feat: integrate GitHub repository listing"
    assert data["author"] == "Alice Developer"
    assert data["timestamp"] == "2026-09-14T09:30:00Z"


# 9. GitHub API failure is handled cleanly.
def test_github_api_failure_handled(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        raise httpx.ConnectError("Connection refused by GitHub")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories")
    assert res.status_code == 502
    assert res.json()["detail"] == "Unable to load GitHub data."


# 10. Rate-limit response is handled.
def test_github_rate_limit_handled(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=403,
            headers={"x-ratelimit-remaining": "0"},
            json={"message": "API rate limit exceeded"},
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories")
    assert res.status_code == 429
    assert "rate limit reached" in res.json()["detail"]


# 11. GitHub credentials are never included in API responses.
def test_github_credentials_never_leaked(monkeypatch):
    _login_test_user()

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json=SAMPLE_RAW_REPOS,
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.get("/api/github/repositories")
    assert res.status_code == 200
    body_text = res.text
    assert MOCK_TOKEN not in body_text
    assert "token" not in body_text.lower()
    assert "secret" not in body_text.lower()


# 12. Arbitrary GitHub URLs and path traversal are rejected.
def test_arbitrary_urls_and_path_traversal_rejected():
    _login_test_user()

    # Path traversal dots in owner parameter
    res1 = client.get("/api/github/repositories/..owner/RepoOne/branches")
    assert res1.status_code == 400
    assert "Invalid repository identifier" in res1.json()["detail"] or "traversal" in res1.json()["detail"]

    # Path traversal dots in repo parameter
    res2 = client.get("/api/github/repositories/allowed_alice/..repo/branches")
    assert res2.status_code == 400

    # Special characters/injection in repo parameter
    res3 = client.get("/api/github/repositories/allowed_alice/repo$bad/branches")
    assert res3.status_code == 400

    # Path traversal in branch query parameter
    res4 = client.get("/api/github/repositories/allowed_alice/RepoOne/commits/latest?branch=../etc/passwd")
    assert res4.status_code == 400
    assert "Invalid branch" in res4.json()["detail"]


# 13. Token missing / session expired requires re-login.
def test_missing_in_memory_token_prompts_relogin():
    # User has cookie, but token was cleared (e.g. server restart)
    user = {"id": MOCK_USER_ID, "username": MOCK_USERNAME}
    session_token = create_session_token(user)
    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)
    clear_all_user_tokens()

    res = client.get("/api/github/repositories")
    assert res.status_code == 401
    assert "GitHub authentication is no longer valid" in res.json()["detail"]
