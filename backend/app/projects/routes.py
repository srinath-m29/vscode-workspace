import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.github.routes import get_authenticated_github_user
from app.projects.manager import (
    open_or_create_workspace,
    get_user_workspace_root,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class OpenProjectRequest(BaseModel):
    owner: str = Field(..., description="GitHub repository owner/organization username")
    repo: str = Field(..., description="GitHub repository name")
    branch: str = Field(..., description="Target git branch to open")


class ProjectWorkspaceResponse(BaseModel):
    status: str = Field(..., description="'ready' or 'dirty'")
    owner: str
    repo: str
    branch: str
    workspace: str = Field(..., description="Absolute server workspace directory path")
    open_url: Optional[str] = Field(None, description="Safe OpenVSCode folder URL for ready workspaces")
    message: Optional[str] = None


@router.post("/open", response_model=ProjectWorkspaceResponse)
async def open_project_endpoint(
    body: OpenProjectRequest,
    auth_ctx: Tuple[Dict[str, Any], str] = Depends(get_authenticated_github_user),
):
    """
    Prepares a safe user-isolated workspace for the requested repository and branch.
    Derives workspace path strictly from the authenticated GitHub numeric ID.
    When ready, validates workspace directory containment and returns open_url.
    """
    session_data, token = auth_ctx
    user_id = session_data["id"]

    result = await open_or_create_workspace(
        token=token,
        user_id=user_id,
        owner=body.owner,
        repo=body.repo,
        branch=body.branch,
        username=session_data.get("username"),
        user_name=session_data.get("name"),
    )

    if result.get("status") == "ready":
        workspace_path = Path(result["workspace"]).resolve()

        # Security validations before returning open_url
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise HTTPException(status_code=500, detail="Prepared workspace directory does not exist.")

        user_root = get_user_workspace_root(user_id).resolve()
        global_root = Path(settings.WORKSPACE_ROOT).resolve()

        try:
            workspace_path.relative_to(user_root)
            workspace_path.relative_to(global_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Workspace path containment violation.")

        # Reject symlink escapes
        if workspace_path.is_symlink():
            try:
                workspace_path.resolve(strict=True).relative_to(user_root)
            except ValueError:
                raise HTTPException(status_code=400, detail="Symlink path traversal detected.")

        # Fully encode complete workspace path as folder query parameter
        # Prefer: urllib.parse.quote(str(workspace_path), safe="") rather than leaving "/" unescaped
        target_path_str = workspace_path.as_posix() if hasattr(workspace_path, "as_posix") else str(workspace_path).replace("\\", "/")
        encoded_path = urllib.parse.quote(str(target_path_str), safe="")
        result["open_url"] = f"/vscode/?folder={encoded_path}"
    else:
        result["open_url"] = None

    return result
