from typing import Optional, Dict, Any, List
import httpx
from app.github.client import github_api_request


def normalize_repository(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a GitHub repository object into the application's clean schema.
    Strips internal GitHub fields and guarantees presence of required attributes.
    """
    owner_login = ""
    if isinstance(raw.get("owner"), dict):
        owner_login = raw["owner"].get("login", "")

    return {
        "id": raw.get("id", 0),
        "name": raw.get("name", ""),
        "full_name": raw.get("full_name", ""),
        "description": raw.get("description") or "",
        "private": bool(raw.get("private", False)),
        "default_branch": raw.get("default_branch", "main"),
        "html_url": raw.get("html_url", ""),
        "language": raw.get("language") or "",
        "updated_at": raw.get("updated_at", ""),
        "owner": owner_login,
    }


async def list_repositories(
    token: str,
    user_id: str | int,
    page: int = 1,
    per_page: int = 30,
    search: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Retrieves and normalizes the authenticated user's repositories from GitHub.
    Only returns repositories the user has legitimate access to (owner, collaborator, org member).
    Supports client search and pagination.
    """
    # Guard pagination params
    safe_page = max(1, page)
    safe_per_page = min(max(1, per_page), 100)

    params = {
        "affiliation": "owner,collaborator,organization_member",
        "sort": "updated",
        "direction": "desc",
        "per_page": safe_per_page,
        "page": safe_page,
    }

    raw_repos = await github_api_request(
        endpoint="user/repos",
        token=token,
        user_id=user_id,
        params=params,
        client=client,
    )

    if not isinstance(raw_repos, list):
        raw_repos = []

    normalized = [normalize_repository(r) for r in raw_repos]

    # Client search filtering if query provided
    if search and search.strip():
        query = search.strip().lower()
        normalized = [
            r for r in normalized
            if query in r["name"].lower()
            or query in r["full_name"].lower()
            or query in r["description"].lower()
        ]

    has_next_page = len(raw_repos) == safe_per_page

    return {
        "repositories": normalized,
        "page": safe_page,
        "per_page": safe_per_page,
        "has_next_page": has_next_page,
    }
