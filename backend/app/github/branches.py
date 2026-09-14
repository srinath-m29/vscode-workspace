from typing import Dict, Any, List, Optional
import httpx
from app.github.client import github_api_request, validate_owner_repo


async def list_branches(
    token: str,
    user_id: str | int,
    owner: str,
    repo: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Retrieves and normalizes branches for a specific repository.
    Identifies the default branch and guarantees validated path parameters.
    """
    validate_owner_repo(owner, repo)

    # 1. Fetch repository metadata to determine the exact default branch
    repo_meta = await github_api_request(
        endpoint=f"repos/{owner}/{repo}",
        token=token,
        user_id=user_id,
        client=client,
    )
    default_branch = repo_meta.get("default_branch", "main")

    # 2. Fetch branch list
    raw_branches = await github_api_request(
        endpoint=f"repos/{owner}/{repo}/branches",
        token=token,
        user_id=user_id,
        params={"per_page": 100},
        client=client,
    )

    if not isinstance(raw_branches, list):
        raw_branches = []

    branches: List[Dict[str, Any]] = []
    has_default_in_list = False

    for b in raw_branches:
        branch_name = b.get("name", "")
        is_default = (branch_name == default_branch)
        if is_default:
            has_default_in_list = True
        branches.append({
            "name": branch_name,
            "default": is_default,
        })

    # If default branch wasn't explicitly in the returned branches page, prepend it
    if not has_default_in_list and default_branch:
        branches.insert(0, {
            "name": default_branch,
            "default": True,
        })

    # Order default branch first, then alphabetical
    branches.sort(key=lambda x: (not x["default"], x["name"].lower()))

    return {
        "branches": branches,
    }
