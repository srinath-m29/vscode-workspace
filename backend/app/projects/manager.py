import os
import re
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import HTTPException
from app.config import settings
from app.github.client import github_api_request
from app.git.validation import validate_git_remote_url
from app.git.credentials import register_workspace_key

logger = logging.getLogger("cloud_ide.projects")

# Strict GitHub identifier validation for owner and repo names.
# Prevents traversal, path injection, null bytes, and arbitrary URLs.
IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")


def validate_identifier(name: str, field_name: str = "identifier") -> None:
    """Validates that owner or repository name conforms strictly to GitHub identifier rules."""
    if not name or not isinstance(name, str):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Must be a non-empty string.",
        )
    if not IDENTIFIER_REGEX.match(name):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Must contain only alphanumeric characters, periods, underscores, or hyphens.",
        )
    if ".." in name or "/" in name or "\\" in name or "\0" in name:
        raise HTTPException(
            status_code=400,
            detail=f"Path traversal or separator characters are not permitted in {field_name}.",
        )


def validate_branch_name(branch: str) -> None:
    """
    Validates git branch ref names. Accepts valid slash-separated paths (e.g. feature/login)
    while rejecting traversal, null bytes, leading dashes, or invalid git ref syntax.
    """
    if not branch or not isinstance(branch, str):
        raise HTTPException(status_code=400, detail="Branch name must be specified.")
    if "\0" in branch or ".." in branch:
        raise HTTPException(status_code=400, detail="Invalid branch name: traversal or null bytes detected.")
    if branch.startswith("-") or branch.startswith("/") or branch.endswith("/"):
        raise HTTPException(status_code=400, detail="Invalid branch name format.")
    # Reject shell metacharacters
    if any(c in branch for c in [";", "&", "|", "`", "$", "(", ")", "<", ">", "\\", '"', "'", "*", "?", "[", "]"]):
        raise HTTPException(status_code=400, detail="Invalid branch name: shell metacharacters detected.")

    # Execute git check-ref-format --branch
    try:
        res = subprocess.run(
            ["git", "check-ref-format", "--branch", branch],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid branch name ref: {res.stderr.strip() or 'malformed git reference'}",
            )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Branch validation timed out.")
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        logger.error(f"Failed to check branch ref format: {exc}")
        raise HTTPException(status_code=400, detail="Invalid branch name.")


def get_user_workspace_root(user_id: str | int) -> Path:
    """
    Derives the authenticated user's isolated workspace root directory:
    /home/workspace/<authenticated_github_user_id>
    Enforces strict containment within global settings.WORKSPACE_ROOT.
    """
    user_id_str = str(user_id).strip()
    if not user_id_str or not user_id_str.isalnum():
        raise HTTPException(status_code=400, detail="Invalid authenticated user identifier.")

    global_root = Path(settings.WORKSPACE_ROOT).resolve()
    user_root = (global_root / user_id_str).resolve()

    try:
        user_root.relative_to(global_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace path containment.")

    return user_root


def get_repo_workspace_path(user_id: str | int, owner: str, repo: str) -> Path:
    """
    Constructs the absolute workspace path for the repository:
    /home/workspace/<authenticated_github_user_id>/<owner>/<repo>
    Verifies that the target path does not escape the user's workspace directory
    or the global workspace root, and blocks symlink traversal.
    """
    validate_identifier(owner, "owner")
    validate_identifier(repo, "repository")

    global_root = Path(settings.WORKSPACE_ROOT).resolve()
    user_root = get_user_workspace_root(user_id)
    target_path = (user_root / owner / repo).resolve()

    # Verify strict containment inside user_root and global_root
    try:
        target_path.relative_to(user_root)
        target_path.relative_to(global_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace path: containment violation.")

    # Reject symlink traversal: if target_path exists and is a symlink, verify realpath
    if target_path.is_symlink():
        real_target = target_path.resolve(strict=True)
        try:
            real_target.relative_to(user_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Symlink path traversal detected.")

    return target_path


def run_git(
    args: List[str],
    cwd: Optional[Path] = None,
    token: Optional[str] = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """
    Executes a git command safely using subprocess array arguments (shell=False).
    Injects ephemeral GIT_ASKPASS credentials strictly into child process environment.
    Tokens are NEVER passed as command arguments, URLs, or written to disk.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    if token:
        askpass_script = Path(__file__).parent / ("askpass.bat" if os.name == "nt" else "askpass.sh")
        env["GIT_ASKPASS"] = str(askpass_script.resolve())
        env["_CLOUDIDE_GIT_TOKEN"] = token

    cmd = ["git"] + args
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return res
    except subprocess.TimeoutExpired:
        logger.error(f"Git command timed out: {args[0] if args else ''}")
        raise HTTPException(status_code=504, detail="Git operation timed out.")


async def verify_github_repository_and_branch(
    token: str,
    user_id: str | int,
    owner: str,
    repo: str,
    branch: str,
) -> None:
    """
    Verifies via GitHub REST API that:
    1. The authenticated user has legitimate access to the repository (public or private).
    2. The requested branch exists on remote.
    """
    # 1. Verify repository access
    try:
        await github_api_request(
            endpoint=f"repos/{owner}/{repo}",
            token=token,
            user_id=user_id,
        )
    except HTTPException as e:
        if e.status_code in (404, 403):
            raise HTTPException(
                status_code=404,
                detail="Repository not found or inaccessible.",
            )
        raise e

    # 2. Verify branch existence
    try:
        await github_api_request(
            endpoint=f"repos/{owner}/{repo}/branches/{branch}",
            token=token,
            user_id=user_id,
        )
    except HTTPException as e:
        if e.status_code in (404, 403):
            raise HTTPException(
                status_code=404,
                detail=f"Branch '{branch}' not found on repository.",
            )
        raise e


def setup_workspace_git_and_vscode(
    workspace_path: Path,
    user_id: str | int,
    owner: str,
    repo: str,
    username: Optional[str] = None,
    user_name: Optional[str] = None,
) -> str:
    """
    Configures git commit identity, ephemeral credential helper, and OpenVSCode terminal
    environment variables for a ready workspace.
    Returns the generated ephemeral workspace key.
    """
    # 1. Verify remote origin URL is clean and matches repository if present
    res_remote = run_git(["config", "--get", "remote.origin.url"], cwd=workspace_path)
    remote_origin = res_remote.stdout.strip()
    if remote_origin:
        validate_git_remote_url(remote_origin, expected_owner=owner, expected_repo=repo)

    # 2. Register ephemeral workspace session key in server memory
    workspace_key = register_workspace_key(workspace_path, user_id)

    # 3. Write fallback key file in .git/cloudide_key with strict permissions
    git_dir = workspace_path / ".git"
    if git_dir.exists():
        key_file = git_dir / "cloudide_key"
        key_file.write_text(workspace_key, encoding="utf-8")
        if os.name != "nt":
            try:
                os.chmod(key_file, 0o600)
            except Exception:
                pass

    # 4. Inject terminal environment into .vscode/settings.json
    vscode_dir = workspace_path / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    vscode_settings = vscode_dir / "settings.json"
    settings_data = {}
    if vscode_settings.exists():
        try:
            settings_data = json.loads(vscode_settings.read_text(encoding="utf-8"))
        except Exception:
            settings_data = {}

    term_env = settings_data.setdefault("terminal.integrated.env.linux", {})
    term_env["GIT_ASKPASS"] = "/usr/local/bin/git-credential-cloudide"
    term_env["CLOUDIDE_WORKSPACE_KEY"] = workspace_key
    vscode_settings.write_text(json.dumps(settings_data, indent=2), encoding="utf-8")

    # 5. Configure local repository Git identity
    display_name = (user_name or username or owner).strip()
    effective_username = (username or owner).strip()
    commit_email = f"{user_id}+{effective_username}@users.noreply.github.com"

    run_git(["config", "user.name", display_name], cwd=workspace_path)
    run_git(["config", "user.email", commit_email], cwd=workspace_path)
    run_git(["config", "credential.helper", "/usr/local/bin/git-credential-cloudide"], cwd=workspace_path)
    run_git(["config", "credential.useHttpPath", "true"], cwd=workspace_path)

    return workspace_key


async def open_or_create_workspace(
    token: str,
    user_id: str | int,
    owner: str,
    repo: str,
    branch: str,
    username: Optional[str] = None,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepares a safe local workspace for the selected repository and branch:
    - User-scoped path: /home/workspace/<user_id>/<owner>/<repo>
    - Clones repository if absent using ephemeral GIT_ASKPASS.
    - If present, checks git status; detects dirty workspaces without modifying user work.
    - If clean, safely updates/checks out the requested branch.
    - Configures commit identity and OpenVSCode terminal credential helper.
    """
    # 1. Validate inputs
    validate_identifier(owner, "owner")
    validate_identifier(repo, "repository")
    validate_branch_name(branch)

    # 2. Verify repository access & branch on remote GitHub
    await verify_github_repository_and_branch(
        token=token,
        user_id=user_id,
        owner=owner,
        repo=repo,
        branch=branch,
    )

    # 3. Derive and validate user-scoped workspace path
    workspace_path = get_repo_workspace_path(user_id, owner, repo)
    remote_url = f"https://github.com/{owner}/{repo}.git"

    # 4. Check if workspace already exists
    if workspace_path.exists():
        # Verify it is a valid Git repository
        git_dir = workspace_path / ".git"
        if not git_dir.exists():
            raise HTTPException(
                status_code=400,
                detail="Existing workspace directory is not a valid Git repository.",
            )

        # Verify origin URL points to the requested owner/repo
        res_remote = run_git(["config", "--get", "remote.origin.url"], cwd=workspace_path)
        configured_origin = res_remote.stdout.strip()
        expected_suffix = f"github.com/{owner}/{repo}".lower()
        if expected_suffix not in configured_origin.lower().replace(".git", ""):
            logger.warning(
                f"Origin mismatch in existing workspace: {configured_origin} vs {expected_suffix}"
            )
            raise HTTPException(
                status_code=400,
                detail="Existing workspace belongs to a different repository.",
            )

        # Check working tree status for uncommitted/staged/untracked changes
        res_status = run_git(["status", "--porcelain"], cwd=workspace_path)
        if res_status.stdout.strip():
            logger.info(f"Workspace {workspace_path} is dirty; returning dirty status without altering files.")
            return {
                "status": "dirty",
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "workspace": str(workspace_path),
                "message": "Workspace contains uncommitted changes. Review and commit your work before switching branches.",
            }

        # Clean workspace: fetch requested branch using ephemeral auth
        res_fetch = run_git(["fetch", "origin", branch], cwd=workspace_path, token=token)
        if res_fetch.returncode != 0:
            logger.error(f"Git fetch failed: {res_fetch.stderr}")
            raise HTTPException(status_code=500, detail="Unable to fetch updates from repository.")

        # Check current branch
        res_curr_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=workspace_path)
        current_branch = res_curr_branch.stdout.strip()

        if current_branch != branch:
            # Check out the branch; if local branch doesn't exist, create it tracking origin
            res_checkout = run_git(["checkout", branch], cwd=workspace_path)
            if res_checkout.returncode != 0:
                res_checkout = run_git(["checkout", "-b", branch, f"origin/{branch}"], cwd=workspace_path)
                if res_checkout.returncode != 0:
                    logger.error(f"Git checkout failed: {res_checkout.stderr}")
                    raise HTTPException(status_code=500, detail="Unable to checkout requested branch.")

        # Merge fast-forward if tracking remote
        run_git(["merge", "--ff-only", f"origin/{branch}"], cwd=workspace_path)

        setup_workspace_git_and_vscode(
            workspace_path=workspace_path,
            user_id=user_id,
            owner=owner,
            repo=repo,
            username=username,
            user_name=user_name,
        )

        return {
            "status": "ready",
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "workspace": str(workspace_path),
        }

    # 5. Workspace does not exist: perform initial clone
    workspace_path.parent.mkdir(parents=True, exist_ok=True)

    clone_args = [
        "clone",
        "--branch",
        branch,
        remote_url,
        str(workspace_path),
    ]

    res_clone = run_git(clone_args, token=token)
    if res_clone.returncode != 0:
        logger.error(f"Git clone failed: {res_clone.stderr}")
        # Clean up failed target directory if left in incomplete state
        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail="Unable to prepare the workspace.",
        )

    setup_workspace_git_and_vscode(
        workspace_path=workspace_path,
        user_id=user_id,
        owner=owner,
        repo=repo,
        username=username,
        user_name=user_name,
    )

    return {
        "status": "ready",
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "workspace": str(workspace_path),
    }
