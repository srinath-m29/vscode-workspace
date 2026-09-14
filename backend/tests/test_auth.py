import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.auth.session import (
    create_session_token,
    create_oauth_state_token,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_allowed_users(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_1", "allowed_alice")
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_2", "99999")  # Numeric ID


def test_oauth_login_redirect_and_state_cookie():
    response = client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    assert "https://github.com/login/oauth/authorize" in response.headers["location"]
    assert "state=" in response.headers["location"]
    assert "scope=" in response.headers["location"]
    assert "read%3Auser" in response.headers["location"]
    assert settings.STATE_COOKIE_NAME in response.cookies


def test_oauth_callback_missing_params():
    response = client.get("/api/auth/callback")
    assert response.status_code == 400


def test_oauth_callback_invalid_state():
    # Provide state param without matching state cookie
    response = client.get("/api/auth/callback?code=sample_code&state=forged_state")
    assert response.status_code == 400
    assert "OAuth state" in response.json()["detail"]


def test_oauth_callback_authorized_by_username(monkeypatch):
    raw_state = "valid-random-oauth-state-abc"
    state_cookie_val = create_oauth_state_token(raw_state)

    async def mock_token_exchange(code, redirect_uri=None, client=None):
        return "mock_gh_token_12345"

    async def mock_fetch_user(token, client=None):
        return {
            "id": 1001,
            "username": "allowed_alice",
            "name": "Alice Developer",
            "avatar_url": "https://github.com/alice.png",
        }

    monkeypatch.setattr("app.auth.routes.exchange_code_for_token", mock_token_exchange)
    monkeypatch.setattr("app.auth.routes.fetch_github_user", mock_fetch_user)

    client.cookies.set(settings.STATE_COOKIE_NAME, state_cookie_val)
    response = client.get(
        f"/api/auth/callback?code=test_code&state={raw_state}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert settings.SESSION_COOKIE_NAME in response.cookies


def test_oauth_callback_authorized_by_numeric_id(monkeypatch):
    raw_state = "valid-random-oauth-state-xyz"
    state_cookie_val = create_oauth_state_token(raw_state)

    async def mock_token_exchange(code, redirect_uri=None, client=None):
        return "mock_gh_token_67890"

    async def mock_fetch_user(token, client=None):
        return {
            "id": 99999,  # Matches ALLOWED_GITHUB_USER_2
            "username": "bob_different_username",
            "name": "Bob Programmer",
            "avatar_url": "https://github.com/bob.png",
        }

    monkeypatch.setattr("app.auth.routes.exchange_code_for_token", mock_token_exchange)
    monkeypatch.setattr("app.auth.routes.fetch_github_user", mock_fetch_user)

    client.cookies.set(settings.STATE_COOKIE_NAME, state_cookie_val)
    response = client.get(
        f"/api/auth/callback?code=test_code&state={raw_state}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert settings.SESSION_COOKIE_NAME in response.cookies


def test_oauth_callback_unauthorized_user_blocked(monkeypatch):
    raw_state = "valid-random-oauth-state-unauth"
    state_cookie_val = create_oauth_state_token(raw_state)

    async def mock_token_exchange(code, redirect_uri=None, client=None):
        return "mock_gh_token_unauth"

    async def mock_fetch_user(token, client=None):
        return {
            "id": 88888,
            "username": "unauthorized_user",
            "name": "Intruder",
            "avatar_url": "",
        }

    monkeypatch.setattr("app.auth.routes.exchange_code_for_token", mock_token_exchange)
    monkeypatch.setattr("app.auth.routes.fetch_github_user", mock_fetch_user)

    client.cookies.set(settings.STATE_COOKIE_NAME, state_cookie_val)
    response = client.get(
        f"/api/auth/callback?code=test_code&state={raw_state}",
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_get_current_user_authenticated():
    user = {"id": 1001, "username": "allowed_alice", "avatar_url": "https://avatar.png"}
    session_token = create_session_token(user)

    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)
    response = client.get("/api/auth/me")

    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["user"]["username"] == "allowed_alice"
    assert data["user"]["id"] == "1001"
    # Ensure no token is leaked
    assert "token" not in data
    assert "access_token" not in data


def test_get_current_user_unauthenticated():
    client.cookies.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_get_current_user_tampered_session():
    client.cookies.set(settings.SESSION_COOKIE_NAME, "tampered.session.token")
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_get_current_user_expired_session(monkeypatch):
    user = {"id": 1001, "username": "allowed_alice"}
    session_token = create_session_token(user)

    monkeypatch.setattr(settings, "SESSION_MAX_AGE_SECONDS", -1)
    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)

    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout():
    user = {"id": 1001, "username": "allowed_alice"}
    session_token = create_session_token(user)

    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)
    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"success": True}


def test_auth_verify_endpoint():
    # 1. Valid authorized session
    user = {"id": 1001, "username": "allowed_alice"}
    session_token = create_session_token(user)
    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)

    res = client.get("/api/auth/verify")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # 2. Missing session
    client.cookies.clear()
    res = client.get("/api/auth/verify")
    assert res.status_code == 401

    # 3. Session for unauthorized user
    unauth_user = {"id": 1234, "username": "stranger"}
    unauth_token = create_session_token(unauth_user)
    client.cookies.set(settings.SESSION_COOKIE_NAME, unauth_token)

    res = client.get("/api/auth/verify")
    assert res.status_code == 401
