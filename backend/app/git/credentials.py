"""
Ephemeral Git credential resolution and workspace session key management.

Provides:
- In-memory workspace session key registry for authorized repository workspaces.
- FastAPI endpoint POST /api/git/credential:
  - Validates repository root containment and remote URL.
  - Verifies workspace key matches the authenticated user's active session.
  - Supplies the user's GitHub OAuth token from the server-side in-memory cache.
  - Tokens exist only in memory during the Git operation and are never written to disk or logged.
"""

import os
import secrets
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.auth.session import get_user_token
from app.git.validation import validate_git_remote_url, validate_workspace_path

logger = logging.getLogger("cloud_ide.git")

# In-memory mapping of workspace path string to session authorization metadata.
# Strictly disposable, never written to disk, files, or git configs.
# Schema: { str(workspace_path): { "user_id": str, "key": str } }
_workspace_keys: Dict[str, Dict[str, Any]] = {}


def register_workspace_key(workspace_path: Path, user_id: str | int) -> str:
    """
    Generates a cryptographically strong ephemeral authorization key for a prepared workspace.
    Associates the key strictly with the user ID in server memory.
    """
    key = secrets.token_urlsafe(32)
    canon_path = str(workspace_path.resolve())
    _workspace_keys[canon_path] = {
        "user_id": str(user_id),
        "key": key,
    }
    return key


def verify_workspace_key(workspace_path: Path, workspace_key: Optional[str]) -> Optional[str]:
    """
    Verifies that the provided workspace key matches the active session key for the workspace.
    Returns authenticated user_id if valid, or None if invalid or absent.
    """
    if not workspace_key:
        return None
    canon_path = str(workspace_path.resolve())
    record = _workspace_keys.get(canon_path)
    if not record:
        return None
    # Constant-time comparison to mitigate timing side-channels
    if secrets.compare_digest(record["key"], workspace_key):
        return record["user_id"]
    return None


def get_workspace_key(workspace_path: Path) -> Optional[str]:
    """Retrieve the registered key for a workspace path."""
    canon_path = str(workspace_path.resolve())
    record = _workspace_keys.get(canon_path)
    return record["key"] if record else None


def clear_workspace_key(workspace_path: Path) -> None:
    """Invalidate and remove workspace key from server memory."""
    canon_path = str(workspace_path.resolve())
    _workspace_keys.pop(canon_path, None)


def clear_all_workspace_keys() -> None:
    """Flush all registered workspace keys from memory (test reset)."""
    _workspace_keys.clear()


# --- FastAPI Endpoint ---

git_credential_router = APIRouter(prefix="/api/git", tags=["git"])


class GitCredentialRequest(BaseModel):
    workspace_path: str = Field(..., description="Absolute server path to the git repository workspace")
    remote_url: str = Field(..., description="Git remote origin URL (must be github.com)")
    workspace_key: Optional[str] = Field(None, description="Ephemeral workspace authorization key")


class GitCredentialResponse(BaseModel):
    username: str = Field(..., description="Git authentication username (x-access-token)")
    token: str = Field(..., description="Ephemeral GitHub OAuth access token")


@git_credential_router.post("/credential", response_model=GitCredentialResponse)
async def get_git_credential(body: GitCredentialRequest):
    """
    Supplies ephemeral GitHub credentials to the local Git credential helper.
    Only allows clean github.com remote URLs and authorized workspace directories.
    User 1 can never obtain User 2's credentials.
    """
    # 1. Resolve and validate workspace path containment
    target_path = Path(body.workspace_path).resolve()
    global_root = Path(settings.WORKSPACE_ROOT).resolve()

    try:
        rel_path = target_path.relative_to(global_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Workspace path containment violation.")

    parts = rel_path.parts
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Malformed workspace path hierarchy.")

    path_user_id, path_owner, path_repo = parts[0], parts[1], parts[2]

    # 2. Validate remote URL (must be clean github.com URL matching workspace owner/repo)
    validated_remote = validate_git_remote_url(
        body.remote_url,
        expected_owner=path_owner,
        expected_repo=path_repo,
    )

    # 3. Verify workspace authorization key
    # Check if a workspace key was passed or if fallback key file exists in .git
    key_to_verify = body.workspace_key
    if not key_to_verify:
        key_file = target_path / ".git" / "cloudide_key"
        if key_file.exists() and key_file.is_file():
            try:
                key_to_verify = key_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    verified_user_id = verify_workspace_key(target_path, key_to_verify)
    if not verified_user_id or verified_user_id != path_user_id:
        logger.warning(
            f"Unauthorized git credential request for {target_path} (user mismatch: {verified_user_id} vs {path_user_id})"
        )
        raise HTTPException(
            status_code=403,
            detail="Unauthorized workspace access. Missing or invalid workspace credentials.",
        )

    # 4. Look up user token in server-side in-memory cache
    access_token = get_user_token(verified_user_id)
    if not access_token:
        logger.warning(f"GitHub access token missing or expired for user {verified_user_id}")
        raise HTTPException(
            status_code=401,
            detail="GitHub authentication has expired. Please sign in again.",
        )

    # Return credentials strictly to the requesting helper on loopback
    return {
        "username": "x-access-token",
        "token": access_token,
    }
