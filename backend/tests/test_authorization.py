import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.auth.session import create_session_token

client = TestClient(app)

USER_1_USERNAME = "authorized_developer_1"
USER_1_ID = 10001

USER_2_USERNAME = "authorized_developer_2"
USER_2_ID = 10002

UNAUTHORIZED_USER_USERNAME = "random_intruder"
UNAUTHORIZED_USER_ID = 99999


@pytest.fixture(autouse=True)
def configure_two_user_allowlist(monkeypatch):
    """
    Configures the system for exactly two authorized users:
    - User 1 allowed by username
    - User 2 allowed by numeric GitHub user ID
    """
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_1", USER_1_USERNAME)
    monkeypatch.setattr(settings, "ALLOWED_GITHUB_USER_2", str(USER_2_ID))


def test_user_1_authorization_success():
    """Test 2: Valid User 1 session is accepted with 200 OK."""
    token = create_session_token({
        "id": USER_1_ID,
        "username": USER_1_USERNAME,
        "avatar_url": "https://avatar.com/user1.png",
    })
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)

    response = client.get("/api/auth/verify")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_user_2_authorization_success():
    """Test 3: Valid User 2 session (authorized by numeric ID) is accepted with 200 OK."""
    token = create_session_token({
        "id": USER_2_ID,
        "username": "user2_changed_username",
        "avatar_url": "https://avatar.com/user2.png",
    })
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)

    response = client.get("/api/auth/verify")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthorized_user_denied():
    """Test 4: Third-party GitHub user is denied with 401 on verify."""
    token = create_session_token({
        "id": UNAUTHORIZED_USER_ID,
        "username": UNAUTHORIZED_USER_USERNAME,
        "avatar_url": "",
    })
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)

    response = client.get("/api/auth/verify")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_missing_session_cookie_denied():
    """Test 1: Request with no session cookie is denied with 401."""
    client.cookies.clear()
    response = client.get("/api/auth/verify")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_tampered_session_cookie_denied():
    """Test 5: Tampered session cookie is denied with 401."""
    valid_token = create_session_token({"id": USER_1_ID, "username": USER_1_USERNAME})
    tampered_token = valid_token[:-4] + "fake"
    client.cookies.set(settings.SESSION_COOKIE_NAME, tampered_token)

    response = client.get("/api/auth/verify")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_expired_session_cookie_denied(monkeypatch):
    """Test 6: Expired session cookie is denied with 401."""
    valid_token = create_session_token({"id": USER_1_ID, "username": USER_1_USERNAME})

    # Simulate expired session
    monkeypatch.setattr(settings, "SESSION_MAX_AGE_SECONDS", -1)
    client.cookies.set(settings.SESSION_COOKIE_NAME, valid_token)

    response = client.get("/api/auth/verify")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_logout_invalidates_verify_access():
    """Test 7: After logout, subsequent access to verify is denied."""
    token = create_session_token({"id": USER_1_ID, "username": USER_1_USERNAME})
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)

    # 1. Before logout: verify passes
    res_before = client.get("/api/auth/verify")
    assert res_before.status_code == 200

    # 2. Perform logout
    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 200

    # 3. Simulate browser receiving Set-Cookie with deletion
    client.cookies.delete(settings.SESSION_COOKIE_NAME)

    # 4. After logout: verify fails with 401
    res_after = client.get("/api/auth/verify")
    assert res_after.status_code == 401


def test_no_sensitive_data_in_verify_response():
    """Verify endpoint must not leak tokens, user IDs, or environment details."""
    token = create_session_token({"id": USER_1_ID, "username": USER_1_USERNAME})
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)

    response = client.get("/api/auth/verify")
    assert response.status_code == 200
    data = response.json()
    assert list(data.keys()) == ["status"]
    assert data["status"] == "ok"
