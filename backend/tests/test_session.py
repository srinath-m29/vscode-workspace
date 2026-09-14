import pytest
from app.auth.session import (
    create_session_token,
    verify_session_token,
    create_oauth_state_token,
    verify_oauth_state_token,
)


def test_session_token_lifecycle():
    user = {
        "id": 12345,
        "username": "testuser",
        "avatar_url": "https://github.com/images/test.png",
        "name": "Test User",
    }
    token = create_session_token(user)
    assert isinstance(token, str)

    verified = verify_session_token(token)
    assert verified is not None
    assert verified["id"] == "12345"
    assert verified["username"] == "testuser"
    assert verified["avatar_url"] == "https://github.com/images/test.png"
    assert verified["name"] == "Test User"


def test_tampered_session_token_rejected():
    user = {"id": 1, "username": "admin"}
    token = create_session_token(user)
    tampered_token = token[:-5] + "XXXXX"

    assert verify_session_token(tampered_token) is None
    assert verify_session_token("invalid.token.structure") is None
    assert verify_session_token(None) is None


def test_expired_session_token_rejected(monkeypatch):
    user = {"id": 1, "username": "admin"}
    token = create_session_token(user)

    from app.config import settings
    monkeypatch.setattr(settings, "SESSION_MAX_AGE_SECONDS", -1)

    assert verify_session_token(token) is None


def test_oauth_state_lifecycle():
    raw_state = "super-secret-random-state-12345"
    token = create_oauth_state_token(raw_state)
    assert isinstance(token, str)

    verified = verify_oauth_state_token(token)
    assert verified == raw_state


def test_tampered_oauth_state_rejected():
    raw_state = "super-secret-state"
    token = create_oauth_state_token(raw_state)
    tampered = token + "bad"

    assert verify_oauth_state_token(tampered) is None
    assert verify_oauth_state_token(None) is None
