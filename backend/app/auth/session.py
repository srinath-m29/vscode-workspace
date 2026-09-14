from typing import Optional, Dict, Any
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import settings

_session_serializer = URLSafeTimedSerializer(
    secret_key=settings.SESSION_SECRET,
    salt="cloudide-auth-session",
)

_state_serializer = URLSafeTimedSerializer(
    secret_key=settings.SESSION_SECRET,
    salt="cloudide-oauth-state",
)


def create_session_token(user_data: Dict[str, Any]) -> str:
    """
    Creates a signed, timestamped session token containing minimal identity fields.
    Does NOT contain GitHub access tokens.
    """
    payload = {
        "id": str(user_data["id"]),
        "username": str(user_data["username"]),
        "avatar_url": str(user_data.get("avatar_url", "")),
        "name": str(user_data.get("name", "")),
    }
    return _session_serializer.dumps(payload)


def verify_session_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Verifies a session token's signature and expiration.
    Returns session dict if valid, or None if invalid/expired.
    """
    if not token:
        return None
    try:
        data = _session_serializer.loads(
            token,
            max_age=settings.SESSION_MAX_AGE_SECONDS,
        )
        if isinstance(data, dict) and "id" in data and "username" in data:
            return data
        return None
    except (BadSignature, SignatureExpired, Exception):
        return None


def create_oauth_state_token(state: str) -> str:
    """Signs an OAuth state string for CSRF mitigation."""
    return _state_serializer.dumps(state)


def verify_oauth_state_token(token: Optional[str]) -> Optional[str]:
    """Verifies an OAuth state cookie's signature and expiration."""
    if not token:
        return None
    try:
        state = _state_serializer.loads(
            token,
            max_age=settings.STATE_MAX_AGE_SECONDS,
        )
        return str(state)
    except (BadSignature, SignatureExpired, Exception):
        return None


# Server-side in-memory token cache for the two authorized users.
# Strictly disposable, never written to disk, files, cookies, or git configs.
_user_access_tokens: Dict[str, str] = {}


def store_user_token(user_id: str | int, access_token: str) -> None:
    """Store GitHub access token securely in server memory keyed by user ID."""
    _user_access_tokens[str(user_id)] = access_token


def get_user_token(user_id: str | int) -> Optional[str]:
    """Retrieve GitHub access token from server memory. Returns None if absent."""
    return _user_access_tokens.get(str(user_id))


def clear_user_token(user_id: str | int) -> None:
    """Invalidate and remove GitHub access token from server memory."""
    _user_access_tokens.pop(str(user_id), None)


def clear_all_user_tokens() -> None:
    """Flush all stored tokens from server memory."""
    _user_access_tokens.clear()
