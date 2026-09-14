import logging
import urllib.parse
from typing import Optional, Dict, Any
import httpx
from app.config import settings

logger = logging.getLogger("cloud_ide.auth")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API_URL = "https://api.github.com/user"


def build_authorization_url(state: str, redirect_uri: Optional[str] = None) -> str:
    """Builds the GitHub OAuth authorization URL."""
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "state": state,
        "scope": settings.GITHUB_OAUTH_SCOPES,
    }
    target_redirect = redirect_uri or settings.GITHUB_REDIRECT_URI
    if target_redirect:
        params["redirect_uri"] = target_redirect

    return f"{GITHUB_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_token(
    code: str,
    redirect_uri: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """
    Exchanges an OAuth authorization code for a temporary GitHub access token.
    Access tokens are never logged.
    """
    payload = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "client_secret": settings.GITHUB_CLIENT_SECRET,
        "code": code,
    }
    target_redirect = redirect_uri or settings.GITHUB_REDIRECT_URI
    if target_redirect:
        payload["redirect_uri"] = target_redirect

    headers = {
        "Accept": "application/json",
        "User-Agent": "Cloud-IDE-Private",
    }

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)
        should_close = True

    try:
        response = await client.post(GITHUB_TOKEN_URL, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(f"GitHub token exchange returned status {response.status_code}")
            raise ValueError("Failed to exchange code with GitHub")

        data = response.json()
        if "error" in data:
            logger.error(f"GitHub token exchange error: {data.get('error_description') or data['error']}")
            raise ValueError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")

        access_token = data.get("access_token")
        if not access_token:
            logger.error("No access_token present in GitHub OAuth response")
            raise ValueError("No access token returned by GitHub")

        return str(access_token)
    finally:
        if should_close:
            await client.aclose()


async def fetch_github_user(
    access_token: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Fetches the authenticated user profile from GitHub API.
    Extracts numeric ID, login, name, and avatar_url.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Cloud-IDE-Private",
    }

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)
        should_close = True

    try:
        response = await client.get(GITHUB_USER_API_URL, headers=headers)
        if response.status_code != 200:
            logger.error(f"GitHub user profile fetch failed with status {response.status_code}")
            raise ValueError("Failed to fetch user profile from GitHub")

        data = response.json()
        if "id" not in data or "login" not in data:
            logger.error("Incomplete user profile returned by GitHub")
            raise ValueError("Incomplete user profile from GitHub")

        return {
            "id": data["id"],
            "username": data["login"],
            "name": data.get("name") or data["login"],
            "avatar_url": data.get("avatar_url") or "",
        }
    finally:
        if should_close:
            await client.aclose()
