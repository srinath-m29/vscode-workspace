import logging
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.github.routes import get_authenticated_github_user
from app.github.client import validate_owner_repo, validate_branch
from app.github.commits import get_latest_commit
from app.projects.manager import get_repo_workspace_path, run_git
from app.deployments.render import (
    trigger_deployment,
    get_deployment,
    get_latest_deployment,
    get_service_details,
    normalize_status,
    extract_live_url,
)

logger = logging.getLogger("cloud_ide.deployments")
router = APIRouter(prefix="/api/deployments", tags=["deployments"])


class TriggerDeployRequest(BaseModel):
    branch: Optional[str] = Field(default="main", description="Target git branch to deploy")
    clearCache: Optional[str] = Field(
        default="do_not_clear",
        description="'do_not_clear' (default) or 'clear'",
    )


class DeploymentTriggerResponse(BaseModel):
    id: str
    status: str
    service: str
    commit: Optional[str] = None
    created_at: Optional[str] = None
    url: Optional[str] = None


class DeploymentStatusResponse(BaseModel):
    status: str
    id: Optional[str] = None
    commit: Optional[str] = None
    url: Optional[str] = None
    created_at: Optional[str] = None


@router.post("/{owner}/{repo}", response_model=DeploymentTriggerResponse)
async def deploy_project(
    owner: str,
    repo: str,
    body: TriggerDeployRequest = TriggerDeployRequest(),
    auth_ctx: Tuple[Dict[str, Any], str] = Depends(get_authenticated_github_user),
):
    """
    Triggers an explicit deployment to Render for a mapped repository.
    Strictly verifies:
    1. Authenticated user and authorized repository.
    2. Server-side Render service mapping (never accepts arbitrary service IDs).
    3. Clean local workspace (rejects dirty/uncommitted files).
    4. Exact HEAD commit SHA pushed to GitHub.
    5. Default 'do_not_clear' for clearCache.
    """
    validate_owner_repo(owner, repo)
    branch = (body.branch or "main").strip()
    validate_branch(branch)

    session_data, token = auth_ctx
    user_id = str(session_data["id"])

    # 1. Resolve server-side Render service mapping
    service_id = settings.get_render_service_id(owner, repo)
    if not service_id:
        logger.warning(f"Unmapped repository deployment attempted: {owner}/{repo}")
        raise HTTPException(
            status_code=400,
            detail="This project is not configured for Render deployment.",
        )

    # 2. Verify workspace state if workspace exists
    workspace_path = get_repo_workspace_path(user_id, owner, repo)
    head_sha = None

    if workspace_path.exists():
        # Check for uncommitted/dirty files
        res_status = run_git(["status", "--porcelain"], cwd=workspace_path)
        if res_status.stdout.strip():
            logger.info(f"Deployment blocked: dirty workspace at {workspace_path}")
            raise HTTPException(
                status_code=400,
                detail="Commit and push your changes before deploying.",
            )

        # Get current HEAD commit SHA
        res_head = run_git(["rev-parse", "HEAD"], cwd=workspace_path)
        if res_head.returncode == 0 and res_head.stdout.strip():
            head_sha = res_head.stdout.strip()

        # Check current branch in workspace
        res_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=workspace_path)
        current_branch = res_branch.stdout.strip()
        if current_branch and current_branch != "HEAD":
            branch = current_branch

    # 3. Verify commit on GitHub branch
    remote_commit = await get_latest_commit(
        token=token,
        user_id=user_id,
        owner=owner,
        repo=repo,
        branch=branch,
    )
    remote_sha = remote_commit.get("sha")

    if not remote_sha:
        raise HTTPException(
            status_code=400,
            detail="Unable to verify latest commit on GitHub.",
        )

    # If workspace exists, ensure local HEAD matches the remote pushed commit
    if head_sha and head_sha != remote_sha:
        logger.info(f"Deployment blocked: local HEAD ({head_sha[:7]}) != remote ({remote_sha[:7]})")
        raise HTTPException(
            status_code=400,
            detail="Commit and push your changes before deploying.",
        )

    deploy_commit_sha = head_sha or remote_sha

    # 4. Trigger deployment via Render API
    clear_cache_val = "clear" if body.clearCache == "clear" else "do_not_clear"
    deploy_data = await trigger_deployment(
        service_id=service_id,
        commit_id=deploy_commit_sha,
        clear_cache=clear_cache_val,
    )

    deploy_id = deploy_data.get("id") or "unknown"
    normalized_status_val = normalize_status(deploy_data.get("status"))

    # 5. Fetch service details for live URL
    service_data = await get_service_details(service_id)
    live_url = extract_live_url(service_data)

    return DeploymentTriggerResponse(
        id=deploy_id,
        status=normalized_status_val,
        service=service_id,
        commit=deploy_commit_sha,
        created_at=deploy_data.get("createdAt"),
        url=live_url,
    )


@router.get("/{owner}/{repo}", response_model=DeploymentStatusResponse)
async def get_latest_deployment_status(
    owner: str,
    repo: str,
    auth_ctx: Tuple[Dict[str, Any], str] = Depends(get_authenticated_github_user),
):
    """
    Retrieves current deployment status for the mapped repository's service.
    """
    validate_owner_repo(owner, repo)
    service_id = settings.get_render_service_id(owner, repo)
    if not service_id:
        raise HTTPException(
            status_code=400,
            detail="This project is not configured for Render deployment.",
        )

    deploy = await get_latest_deployment(service_id)
    service_data = await get_service_details(service_id)
    live_url = extract_live_url(service_data)

    if not deploy:
        return DeploymentStatusResponse(
            status="unknown",
            id=None,
            commit=None,
            url=live_url,
            created_at=None,
        )

    commit_info = deploy.get("commit")
    commit_sha = None
    if isinstance(commit_info, dict):
        commit_sha = commit_info.get("id")
    elif isinstance(commit_info, str):
        commit_sha = commit_info

    return DeploymentStatusResponse(
        status=normalize_status(deploy.get("status")),
        id=deploy.get("id"),
        commit=commit_sha,
        url=live_url,
        created_at=deploy.get("createdAt"),
    )


@router.get("/{owner}/{repo}/{deploy_id}", response_model=DeploymentStatusResponse)
async def get_exact_deployment_status(
    owner: str,
    repo: str,
    deploy_id: str,
    auth_ctx: Tuple[Dict[str, Any], str] = Depends(get_authenticated_github_user),
):
    """
    Retrieves exact deployment status by deploy_id (used for polling the initiated deploy).
    Prevents race conditions where multiple deployments may exist.
    """
    validate_owner_repo(owner, repo)
    service_id = settings.get_render_service_id(owner, repo)
    if not service_id:
        raise HTTPException(
            status_code=400,
            detail="This project is not configured for Render deployment.",
        )

    deploy = await get_deployment(service_id, deploy_id.strip())
    service_data = await get_service_details(service_id)
    live_url = extract_live_url(service_data)

    commit_info = deploy.get("commit")
    commit_sha = None
    if isinstance(commit_info, dict):
        commit_sha = commit_info.get("id")
    elif isinstance(commit_info, str):
        commit_sha = commit_info

    return DeploymentStatusResponse(
        status=normalize_status(deploy.get("status")),
        id=deploy.get("id", deploy_id),
        commit=commit_sha,
        url=live_url,
        created_at=deploy.get("createdAt"),
    )
