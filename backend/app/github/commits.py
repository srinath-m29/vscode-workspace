from typing import Dict, Any, Optional
import httpx
from fastapi import HTTPException
from app.github.client import (
    github_api_request,
    validate_owner_repo,
    validate_branch,
)


async def get_latest_commit(
    token: str,
    user_id: str | int,
    owner: str,
    repo: str,
    branch: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Retrieves the latest commit for a specific repository branch.
    Guarantees validation of owner, repo, and branch parameters.
    """
    validate_owner_repo(owner, repo)
    validate_branch(branch)

    params = {
        "sha": branch,
        "per_page": 1,
    }

    raw_commits = await github_api_request(
        endpoint=f"repos/{owner}/{repo}/commits",
        token=token,
        user_id=user_id,
        params=params,
        client=client,
    )

    if not isinstance(raw_commits, list) or len(raw_commits) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No commits found on branch '{branch}'.",
        )

    latest = raw_commits[0]
    commit_details = latest.get("commit", {})
    author_details = commit_details.get("author") or {}
    committer_details = commit_details.get("committer") or {}

    raw_message = commit_details.get("message", "")
    short_message = raw_message.split("\n")[0].strip() if raw_message else "No commit message"

    author_name = (
        author_details.get("name")
        or (latest.get("author") or {}).get("login")
        or "Unknown"
    )
    timestamp = author_details.get("date") or committer_details.get("date") or ""

    return {
        "sha": latest.get("sha", ""),
        "message": short_message,
        "author": author_name,
        "timestamp": timestamp,
    }
