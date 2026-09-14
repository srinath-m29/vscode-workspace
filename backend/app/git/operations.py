"""
Safe Git operations wrapper for Cloud IDE backend.

Enforces:
- All git commands execute via subprocess.run(..., shell=False).
- User and workspace path containment validation before any operation.
- Non-destructive git pull (never forces reset --hard or git clean -fd).
- Ephemeral credential helper injection without exposing tokens in arguments or logs.
- Safe Git user identity configuration using GitHub verified or noreply email.
"""

import os
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import HTTPException
from app.config import settings
from app.git.validation import validate_workspace_path, validate_git_remote_url
from app.git.credentials import get_workspace_key

logger = logging.getLogger("cloud_ide.git")


def configure_git_identity(
    workspace_path: Path,
    user_id: str | int,
    username: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    helper_path: Optional[str] = None,
) -> None:
    """
    Configures local repository git identity and credential helper.

    Git identity:
    - user.name: Full display name or GitHub username.
    - user.email: GitHub verified email or official GitHub noreply email (<id>+<username>@users.noreply.github.com).
    - credential.helper: /usr/local/bin/git-credential-cloudide
    - credential.useHttpPath: true

    Credentials/tokens are NEVER stored in .git/config.
    """
    validate_workspace_path(workspace_path, user_id)

    commit_name = (name or username).strip()
    if email and "@" in email:
        commit_email = email.strip()
    else:
        # Official GitHub safe noreply email format
        commit_email = f"{user_id}+{username}@users.noreply.github.com"

    # Set user.name and user.email in local repository config
    subprocess.run(["git", "config", "user.name", commit_name], cwd=workspace_path, check=True)
    subprocess.run(["git", "config", "user.email", commit_email], cwd=workspace_path, check=True)

    # Configure credential helper in local repository config
    cred_helper = helper_path or "/usr/local/bin/git-credential-cloudide"
    subprocess.run(["git", "config", "credential.helper", cred_helper], cwd=workspace_path, check=True)
    subprocess.run(["git", "config", "credential.useHttpPath", "true"], cwd=workspace_path, check=True)


def run_git_secure(
    args: List[str],
    workspace_path: Path,
    user_id: str | int,
    helper_path: Optional[str] = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """
    Executes a git command inside the validated user workspace using shell=False.
    Injects GIT_ASKPASS pointing to git-credential-cloudide and the workspace session key.
    Tokens are NEVER passed as command-line arguments.
    """
    validate_workspace_path(workspace_path, user_id)

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    # Resolve helper executable
    default_helper = helper_path or "/usr/local/bin/git-credential-cloudide"
    if not Path(default_helper).exists():
        # Fall back to local repository scripts/git-credential-cloudide if running locally
        local_script = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "git-credential-cloudide"
        if local_script.exists():
            default_helper = str(local_script.resolve())

    env["GIT_ASKPASS"] = default_helper

    # Supply workspace session key for server-side verification
    workspace_key = get_workspace_key(workspace_path)
    if workspace_key:
        env["CLOUDIDE_WORKSPACE_KEY"] = workspace_key

    cmd = ["git"] + args
    try:
        res = subprocess.run(
            cmd,
            cwd=workspace_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return res
    except subprocess.TimeoutExpired:
        logger.error(f"Git operation timed out: {args[0] if args else ''}")
        raise HTTPException(status_code=504, detail="Git operation timed out.")


def git_status(workspace_path: Path, user_id: str | int) -> Dict[str, Any]:
    """
    Checks git status for the repository workspace without modifying the working tree.
    """
    res = run_git_secure(["status", "--porcelain", "-b"], workspace_path, user_id)
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git status failed: {res.stderr.strip()}")

    lines = [line for line in res.stdout.splitlines() if line.strip()]
    branch_line = lines[0] if lines and lines[0].startswith("##") else "## unknown"
    changed_files = [line for line in lines if not line.startswith("##")]

    return {
        "is_clean": len(changed_files) == 0,
        "branch": branch_line.lstrip("#").strip(),
        "changed_files": changed_files,
        "output": res.stdout,
    }


def git_add(
    workspace_path: Path,
    user_id: str | int,
    files: Optional[List[str]] = None,
) -> None:
    """
    Stages specified files or all changes in the repository.
    """
    target_files = files if files else ["."]
    res = run_git_secure(["add"] + target_files, workspace_path, user_id)
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git add failed: {res.stderr.strip()}")


def git_commit(
    workspace_path: Path,
    user_id: str | int,
    message: str,
) -> str:
    """
    Records a git commit in the workspace.
    """
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Commit message must be non-empty.")

    res = run_git_secure(["commit", "-m", message.strip()], workspace_path, user_id)
    if res.returncode != 0:
        raise HTTPException(status_code=400, detail=f"git commit failed: {res.stderr.strip()}")

    # Retrieve new commit SHA
    res_sha = run_git_secure(["rev-parse", "HEAD"], workspace_path, user_id)
    return res_sha.stdout.strip()


def git_fetch(
    workspace_path: Path,
    user_id: str | int,
    remote: str = "origin",
    branch: Optional[str] = None,
    helper_path: Optional[str] = None,
) -> None:
    """
    Fetches remote updates using the ephemeral Git credential helper.
    """
    args = ["fetch", remote]
    if branch:
        args.append(branch)

    res = run_git_secure(args, workspace_path, user_id, helper_path=helper_path)
    if res.returncode != 0:
        stderr_msg = res.stderr.strip()
        if "Authentication failed" in stderr_msg or "could not read Username" in stderr_msg:
            raise HTTPException(
                status_code=401,
                detail="GitHub authentication has expired. Please sign in again.",
            )
        raise HTTPException(status_code=500, detail="Failed to fetch updates from remote repository.")


def git_pull(
    workspace_path: Path,
    user_id: str | int,
    remote: str = "origin",
    branch: Optional[str] = None,
    helper_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pulls updates from remote branch while strictly protecting uncommitted work.
    Never executes git reset --hard or git clean -fd.
    """
    # 1. Verify working tree cleanliness
    status = git_status(workspace_path, user_id)
    if not status["is_clean"]:
        return {
            "status": "dirty",
            "message": "Workspace contains uncommitted changes. Commit your work before pulling.",
            "changed_files": status["changed_files"],
        }

    # 2. Fetch and merge fast-forward
    args = ["pull", "--ff-only", remote]
    if branch:
        args.append(branch)

    res = run_git_secure(args, workspace_path, user_id, helper_path=helper_path)
    if res.returncode != 0:
        stderr_msg = res.stderr.strip()
        if "Authentication failed" in stderr_msg or "could not read Username" in stderr_msg:
            raise HTTPException(
                status_code=401,
                detail="GitHub authentication has expired. Please sign in again.",
            )
        raise HTTPException(status_code=500, detail=f"git pull failed: {stderr_msg}")

    return {
        "status": "success",
        "output": res.stdout.strip(),
    }


def git_push(
    workspace_path: Path,
    user_id: str | int,
    remote: str = "origin",
    branch: Optional[str] = None,
    helper_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pushes local branch commits to authorized remote repository via ephemeral credentials.
    """
    # Determine branch if not specified
    if not branch:
        res_branch = run_git_secure(["rev-parse", "--abbrev-ref", "HEAD"], workspace_path, user_id)
        target_branch = res_branch.stdout.strip()
    else:
        target_branch = branch

    args = ["push", remote, target_branch]
    res = run_git_secure(args, workspace_path, user_id, helper_path=helper_path)

    if res.returncode != 0:
        stderr_msg = res.stderr.strip()
        if "Authentication failed" in stderr_msg or "could not read Username" in stderr_msg:
            raise HTTPException(
                status_code=401,
                detail="GitHub authentication has expired. Please sign in again.",
            )
        raise HTTPException(status_code=500, detail=f"git push failed: {stderr_msg}")

    return {
        "status": "success",
        "output": res.stdout.strip() or res.stderr.strip(),
    }
