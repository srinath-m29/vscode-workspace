import logging
from typing import Optional, Dict, Any, Tuple
from fastapi import APIRouter, Request, HTTPException, Depends, Query

from app.config import settings
from app.auth.session import verify_session_token, get_user_token
from app.github.repositories import list_repositories
from app.github.branches import list_branches
from app.github.commits import get_latest_commit

logger = logging.getLogger("cloud_ide.github")

router = APIRouter(prefix="/api/github", tags=["github"])


async def get_authenticated_github_user(request: Request) -> Tuple[Dict[str, Any], str]:
    """
    Dependency ensuring request comes from an authenticated, authorized user
    with an active server-side GitHub access token in memory.
    """
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_data = verify_session_token(session_cookie)

    if not session_data or not settings.is_user_authorized(
        username=session_data.get("username", ""),
        user_id=session_data.get("id"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in.",
        )

    user_id = str(session_data["id"])
    token = get_user_token(user_id)

    if not token:
        logger.warning(f"No in-memory token found for authenticated user {session_data.get('username')}")
        raise HTTPException(
            status_code=401,
            detail="GitHub authentication is no longer valid. Please sign in again.",
        )

    return session_data, token


@router.get("/repositories")
async def get_repositories_endpoint(
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    auth_ctx: Tuple[Dict[str, Any], str] = Depends(get_authenticated_github_user),
):
    """
    Lists repositories accessible to the authenticated GitHub user.
    Supports server-side search filtering and pagination.
    """
    session_data, token = auth_ctx
    return await list_repositories(
        token=token,
        user_id=session_data["id"],
        page=page,
        per_page=per_page,
        search=search,
    )


@router.get("/repositories/{owner}/{repo}/branches")
async def get_branches_endpoint(
    owner: str,
    repo: str,
    auth_ctx: Tuple[Dict[str, Any], str] = Depends(get_authenticated_github_user),
):
    """
    Lists branches for a given repository and marks the default branch.
    Guarantees server-side path parameter validation.
    """
    session_data, token = auth_ctx
    return await list_branches(
        token=token,
        user_id=session_data["id"],
        owner=owner,
        repo=repo,
    )


@router.get("/repositories/{owner}/{repo}/commits/latest")
async def get_latest_commit_endpoint(
    owner: str,
    repo: str,
    branch: str = Query(..., description="Branch name to fetch latest commit from"),
    auth_ctx: Tuple[Dict[str, Any], str] = Depends(get_authenticated_github_user),
):
    """
    Retrieves the latest commit details on a specific repository branch.
    """
    session_data, token = auth_ctx
    return await get_latest_commit(
        token=token,
        user_id=session_data["id"],
        owner=owner,
        repo=repo,
        branch=branch,
    )
