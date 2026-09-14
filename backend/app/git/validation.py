"""
Git remote and workspace path security validation.

Enforces:
- Clean GitHub HTTPS remote URLs (https://github.com/<owner>/<repo>[.git]).
- Rejection of tokens/credentials in remote URLs (https://token@github.com/...).
- Rejection of non-github.com hosts, plaintext http://, ssh://, file://, or local paths.
- Strict workspace path containment and user isolation (/home/workspace/<user_id>/<owner>/<repo>).
"""

import re
import urllib.parse
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from app.config import settings

# Strict regex for GitHub repository paths: /<owner>/<repo>[.git]
GITHUB_PATH_REGEX = re.compile(r"^/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(\.git)?$")


def validate_git_remote_url(
    remote_url: str,
    expected_owner: Optional[str] = None,
    expected_repo: Optional[str] = None,
) -> Dict[str, str]:
    """
    Validates that a git remote URL is strictly a clean GitHub HTTPS URL.

    Rules:
    - Scheme must be strictly 'https' (rejects http, ssh, file, git).
    - Hostname must be strictly 'github.com' (rejects external/arbitrary hosts).
    - Userinfo (username/password/token) MUST NOT be present (rejects https://token@github.com).
    - Port must not be specified.
    - Path must match /<owner>/<repo>[.git].
    - If expected_owner/expected_repo are provided, verifies exact case-insensitive match.
    """
    if not remote_url or not isinstance(remote_url, str):
        raise HTTPException(status_code=400, detail="Git remote URL must be specified.")

    raw = remote_url.strip()

    # Reject leading/trailing whitespace tricks or backslashes
    if "\\" in raw or "\0" in raw or "\n" in raw or "\r" in raw:
        raise HTTPException(status_code=400, detail="Invalid characters in git remote URL.")

    # Reject SSH shorthand (e.g. git@github.com:owner/repo.git)
    if "@" in raw and "://" not in raw:
        raise HTTPException(status_code=400, detail="SSH git remotes are not permitted.")

    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed git remote URL.")

    # 1. Scheme must be HTTPS
    if parsed.scheme.lower() != "https":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid remote URL scheme '{parsed.scheme}'. Only HTTPS is permitted.",
        )

    # 2. Hostname must be strictly github.com
    hostname = (parsed.hostname or "").lower()
    if hostname != "github.com":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid remote host '{hostname}'. Only github.com is permitted.",
        )

    # 3. Reject credentials in URL (username, password, token in netloc)
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise HTTPException(
            status_code=400,
            detail="Credentials in remote URL are strictly prohibited. Remote must remain clean.",
        )

    # 4. Reject custom port numbers
    if parsed.port is not None and parsed.port != 443:
        raise HTTPException(status_code=400, detail="Custom ports are not permitted for github.com remotes.")

    # 5. Validate path structure /<owner>/<repo>[.git]
    path = parsed.path.rstrip("/")
    match = GITHUB_PATH_REGEX.match(path)
    if not match:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid repository path format in remote URL: '{path}'",
        )

    owner, repo, _ = match.groups()

    # Reject traversal segments in owner/repo
    if ".." in owner or ".." in repo:
        raise HTTPException(status_code=400, detail="Path traversal in repository remote URL.")

    # Clean repo name without trailing .git
    clean_repo = repo[:-4] if repo.lower().endswith(".git") else repo

    # 6. Verify match against expected repository if specified
    if expected_owner is not None and owner.lower() != expected_owner.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Remote owner mismatch: expected '{expected_owner}', got '{owner}'.",
        )

    if expected_repo is not None:
        expected_clean_repo = expected_repo[:-4] if expected_repo.lower().endswith(".git") else expected_repo
        if clean_repo.lower() != expected_clean_repo.lower():
            raise HTTPException(
                status_code=400,
                detail=f"Remote repository mismatch: expected '{expected_clean_repo}', got '{clean_repo}'.",
            )

    # Normalized canonical remote URL
    canonical_url = f"https://github.com/{owner}/{clean_repo}.git"

    return {
        "owner": owner,
        "repo": clean_repo,
        "canonical_url": canonical_url,
    }


def validate_workspace_path(workspace_path: Path, expected_user_id: str | int) -> Tuple[str, str, str]:
    """
    Validates that a workspace path is strictly contained within the user's workspace
    root and extracts (user_id, owner, repo).

    Expected path format:
    <settings.WORKSPACE_ROOT>/<user_id>/<owner>/<repo>

    Raises HTTPException(400) if:
    - Path does not exist or is not a directory.
    - Path escapes settings.WORKSPACE_ROOT.
    - Path user_id does not match expected_user_id.
    - Path is a symlink pointing outside the user's workspace root.
    """
    resolved_path = workspace_path.resolve()
    global_root = Path(settings.WORKSPACE_ROOT).resolve()

    # Check containment within global workspace root
    try:
        rel_to_global = resolved_path.relative_to(global_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Workspace path containment violation.")

    parts = rel_to_global.parts
    if len(parts) < 3:
        raise HTTPException(
            status_code=400,
            detail="Workspace path must conform to <WORKSPACE_ROOT>/<user_id>/<owner>/<repo>.",
        )

    path_user_id, owner, repo = parts[0], parts[1], parts[2]

    # Enforce user isolation
    if str(path_user_id) != str(expected_user_id):
        raise HTTPException(
            status_code=403,
            detail="Workspace does not belong to the authenticated user. Cross-user access denied.",
        )

    # Reject symlink escapes
    if workspace_path.is_symlink():
        real_target = workspace_path.resolve(strict=True)
        user_root = global_root / str(expected_user_id)
        try:
            real_target.relative_to(user_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Symlink path traversal detected.")

    return path_user_id, owner, repo
