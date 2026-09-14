import secrets
import logging
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse

from app.config import settings
from app.auth.session import (
    create_session_token,
    verify_session_token,
    create_oauth_state_token,
    verify_oauth_state_token,
    store_user_token,
    clear_user_token,
)
from app.auth.github_oauth import (
    build_authorization_url,
    exchange_code_for_token,
    fetch_github_user,
)
from app.github.client import invalidate_user_cache

logger = logging.getLogger("cloud_ide.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login(response: Response):
    """
    Initiates GitHub OAuth flow.
    Generates a secure state, stores in an HttpOnly cookie, and redirects to GitHub.
    """
    raw_state = secrets.token_urlsafe(32)
    state_cookie_value = create_oauth_state_token(raw_state)

    redirect_url = build_authorization_url(raw_state)
    res = RedirectResponse(url=redirect_url, status_code=302)

    res.set_cookie(
        key=settings.STATE_COOKIE_NAME,
        value=state_cookie_value,
        max_age=settings.STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return res


@router.get("/callback")
async def callback(request: Request, response: Response, code: str = "", state: str = ""):
    """
    GitHub OAuth callback endpoint.
    Validates state cookie, exchanges authorization code for token,
    checks 2-user allowlist, and sets a signed session cookie.
    """
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state parameter.")

    # Validate state from cookie
    state_cookie = request.cookies.get(settings.STATE_COOKIE_NAME)
    expected_state = verify_oauth_state_token(state_cookie)
    if not expected_state or expected_state != state:
        logger.warning("OAuth callback rejected: state mismatch or expired")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    # Exchange code for access token
    try:
        access_token = await exchange_code_for_token(code)
    except Exception as e:
        logger.error(f"OAuth token exchange failed: {e}")
        raise HTTPException(status_code=400, detail="GitHub authentication failed.")

    # Retrieve authenticated user profile
    try:
        user_profile = await fetch_github_user(access_token)
    except Exception as e:
        logger.error(f"Fetching GitHub user profile failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to retrieve GitHub user profile.")

    # Enforce two-user security model
    if not settings.is_user_authorized(
        username=user_profile["username"],
        user_id=user_profile["id"],
    ):
        logger.warning(
            f"Unauthorized user attempted login: {user_profile['username']} (ID: {user_profile['id']})"
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied. This private IDE is limited to two authorized users.",
        )

    # Store GitHub access token strictly in server RAM (never in cookies or client responses)
    store_user_token(user_profile["id"], access_token)

    # Issue signed session cookie (contains identity only, NO access token)
    session_token = create_session_token(user_profile)

    res = RedirectResponse(url="/", status_code=302)
    res.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )

    # Clear state cookie
    res.delete_cookie(
        key=settings.STATE_COOKIE_NAME,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )

    logger.info(f"Authorized login successful: {user_profile['username']}")
    return res


@router.get("/me")
async def get_current_user(request: Request):
    """
    Returns the current authenticated user identity from the signed session cookie.
    Never returns GitHub access tokens.
    """
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_data = verify_session_token(session_cookie)

    if not session_data or not settings.is_user_authorized(
        username=session_data["username"],
        user_id=session_data["id"],
    ):
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")

    return {
        "authenticated": True,
        "user": {
            "id": session_data["id"],
            "username": session_data["username"],
            "avatar_url": session_data.get("avatar_url", ""),
            "name": session_data.get("name", ""),
        },
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Logs out the user, invalidates cached access tokens and session cookies.
    """
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_data = verify_session_token(session_cookie)
    if session_data and "id" in session_data:
        clear_user_token(session_data["id"])
        invalidate_user_cache(session_data["id"])

    res = Response(content='{"success": true}', media_type="application/json")
    res.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return res


@router.get("/verify")
async def verify_auth(request: Request):
    """
    Lightweight auth verification endpoint for NGINX auth_request subrequests.
    Returns 200 OK for valid session of authorized user, or 401 Unauthorized.
    """
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_data = verify_session_token(session_cookie)

    if not session_data or not settings.is_user_authorized(
        username=session_data["username"],
        user_id=session_data["id"],
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"status": "ok"}
