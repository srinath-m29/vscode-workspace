import time
import re
import logging
from typing import Optional, Dict, Any, Tuple
import httpx
from fastapi import HTTPException
from app.auth.session import clear_user_token

logger = logging.getLogger("cloud_ide.github")

GITHUB_API_BASE_URL = "https://api.github.com"
CACHE_TTL_SECONDS = 60.0

# Regex for safe GitHub identifiers (owner, repository names)
# GitHub allows alphanumeric characters, hyphens, underscores, and periods.
# Prevents directory traversal (..), path injection, control chars, and SSRF.
REPO_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")

# Regex for safe git branch names
BRANCH_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_./-]+$")

# Disposable in-memory response cache: (user_id, endpoint, query) -> (timestamp, data)
_github_cache: Dict[str, Tuple[float, Any]] = {}


def validate_owner_repo(owner: str, repo: str) -> None:
    """
    Validates owner and repository names to prevent path traversal,
    arbitrary URL injection, and malformed inputs.
    """
    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Owner and repository must be specified.")
    if not REPO_IDENTIFIER_REGEX.match(owner) or not REPO_IDENTIFIER_REGEX.match(repo):
        raise HTTPException(status_code=400, detail="Invalid repository identifier.")
    if ".." in owner or ".." in repo:
        raise HTTPException(status_code=400, detail="Path traversal is not permitted.")


def validate_branch(branch: str) -> None:
    """
    Validates branch name format according to git reference conventions.
    """
    if not branch:
        raise HTTPException(status_code=400, detail="Branch name must be specified.")
    if not BRANCH_NAME_REGEX.match(branch):
        raise HTTPException(status_code=400, detail="Invalid branch name.")
    if ".." in branch or branch.startswith("/") or branch.endswith("/"):
        raise HTTPException(status_code=400, detail="Invalid branch name format.")


def invalidate_user_cache(user_id: str | int) -> None:
    """
    Invalidates all cached GitHub API responses for a specific user.
    Invoked upon logout or authentication failure.
    """
    prefix = f"{user_id}:"
    keys_to_remove = [k for k in _github_cache if k.startswith(prefix)]
    for k in keys_to_remove:
        _github_cache.pop(k, None)


def clear_all_github_cache() -> None:
    """Flushes entire in-memory GitHub cache."""
    _github_cache.clear()


async def github_api_request(
    endpoint: str,
    token: str,
    user_id: str | int,
    params: Optional[Dict[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
    use_cache: bool = True,
) -> Any:
    """
    Makes a secure, server-side HTTP request to GitHub REST API.
    Enforces authentication, 60s TTL caching, and error normalization.
    """
    # Reject arbitrary URLs - only allow relative endpoints appended to GITHUB_API_BASE_URL
    if endpoint.startswith("http://") or endpoint.startswith("https://") or endpoint.startswith("//"):
        raise HTTPException(status_code=400, detail="Arbitrary GitHub URLs are not permitted.")

    clean_endpoint = endpoint.lstrip("/")
    url = f"{GITHUB_API_BASE_URL}/{clean_endpoint}"

    # Build cache key
    params_str = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    cache_key = f"{user_id}:GET:{clean_endpoint}:{params_str}"

    if use_cache and cache_key in _github_cache:
        cached_time, cached_data = _github_cache[cache_key]
        if time.time() - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Cloud-IDE-Private",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)
        should_close = True

    try:
        response = await client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:
        logger.error(f"GitHub API network failure: {exc}")
        raise HTTPException(status_code=502, detail="Unable to load GitHub data.")
    finally:
        if should_close:
            await client.aclose()

    # Rate limiting handling
    if response.status_code == 429 or (
        response.status_code == 403
        and (
            response.headers.get("x-ratelimit-remaining") == "0"
            or "rate limit" in response.text.lower()
        )
    ):
        logger.warning(f"GitHub API rate limit encountered for user {user_id}")
        raise HTTPException(
            status_code=429,
            detail="GitHub API rate limit reached. Please try again later.",
        )

    # Auth failure handling
    if response.status_code == 401:
        logger.warning(f"GitHub token rejected for user {user_id} - invalidating session token")
        invalidate_user_cache(user_id)
        clear_user_token(user_id)
        raise HTTPException(
            status_code=401,
            detail="GitHub authentication is no longer valid. Please sign in again.",
        )

    # Repository access permissions / not found
    if response.status_code in (403, 404):
        logger.warning(
            f"GitHub API returned {response.status_code} for endpoint {clean_endpoint} (user: {user_id})"
        )
        raise HTTPException(
            status_code=response.status_code,
            detail="Unable to access this repository.",
        )

    if response.status_code != 200:
        logger.error(
            f"GitHub API unexpected status {response.status_code} for {clean_endpoint}"
        )
        raise HTTPException(
            status_code=response.status_code if response.status_code < 500 else 502,
            detail="Unable to load GitHub data.",
        )

    data = response.json()

    # Cache successful response in RAM
    if use_cache:
        _github_cache[cache_key] = (time.time(), data)

    return data
