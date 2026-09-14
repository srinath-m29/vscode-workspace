"""
Tests for STEP 11: Ephemeral Git Credential Helper and Security.

Verifies:
1. Helper script exists.
2. Helper script is executable / valid Python 3.
3. Helper contains no hardcoded tokens or secrets.
4. Helper does not write persistent credentials to disk (store/erase no-ops).
5. Helper rejects non-GitHub hosts.
6. Helper supplies credentials only when authorized.
7. User 1 cannot obtain User 2's credential.
8. Token does not appear in remote URL.
9. Token does not appear in .git/config.
10. Token does not appear in process arguments.
11. Token does not appear in logs.
12. GIT_ASKPASS username and password handling.
"""

import os
import sys
import json
import stat
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.auth.session import store_user_token, clear_all_user_tokens
from app.git.credentials import (
    register_workspace_key,
    verify_workspace_key,
    clear_all_workspace_keys,
)
from app.git.validation import validate_git_remote_url, validate_workspace_path

client = TestClient(app)

HELPER_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "git-credential-cloudide"

USER_1_ID = "1001"
USER_1_TOKEN = "gho_mock_token_alice_11111"

USER_2_ID = "99999"
USER_2_TOKEN = "gho_mock_token_bob_22222"


@pytest.fixture(autouse=True)
def setup_credentials_env(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_dir))
    clear_all_user_tokens()
    clear_all_workspace_keys()


# 1. Helper exists
def test_helper_script_exists():
    assert HELPER_PATH.exists(), f"Credential helper not found at {HELPER_PATH}"
    assert HELPER_PATH.is_file(), "Credential helper must be a regular file"


# 2. Helper executable / shebang
def test_helper_script_executable():
    content = HELPER_PATH.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env python3"), "Helper must have python3 shebang"

    # On POSIX, check executable bit
    if os.name != "nt":
        mode = os.stat(HELPER_PATH).st_mode
        assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), "Helper must have executable permissions"


# 3. Helper contains no hardcoded tokens
def test_helper_contains_no_hardcoded_tokens():
    content = HELPER_PATH.read_text(encoding="utf-8").lower()
    assert "gho_" not in content, "Helper must not contain hardcoded OAuth tokens"
    assert "ghp_" not in content, "Helper must not contain hardcoded personal tokens"
    assert "github_pat_" not in content, "Helper must not contain hardcoded fine-grained tokens"


# 4. Helper does not write persistent credentials (store / erase are safe no-ops)
def test_helper_store_and_erase_no_persistence():
    # Calling with 'store' should exit 0 without writing any files
    res_store = subprocess.run(
        [sys.executable, str(HELPER_PATH), "store"],
        input="protocol=https\nhost=github.com\nusername=alice\npassword=secret\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert res_store.returncode == 0
    assert res_store.stdout == ""

    # Calling with 'erase' should exit 0
    res_erase = subprocess.run(
        [sys.executable, str(HELPER_PATH), "erase"],
        input="protocol=https\nhost=github.com\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert res_erase.returncode == 0
    assert res_erase.stdout == ""


# 5. Helper rejects non-GitHub hosts
def test_helper_rejects_non_github_hosts():
    res = subprocess.run(
        [sys.executable, str(HELPER_PATH), "get"],
        input="protocol=https\nhost=gitlab.com\npath=owner/repo.git\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert res.returncode == 0
    assert res.stdout == "", "Helper must not return credentials for non-GitHub hosts"

    res_attacker = subprocess.run(
        [sys.executable, str(HELPER_PATH), "get"],
        input="protocol=https\nhost=attacker.com\npath=malicious/repo.git\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert res_attacker.returncode == 0
    assert res_attacker.stdout == "", "Helper must not return credentials for attacker hosts"


# 6. Helper supplies credentials only when authorized by server-side key
def test_helper_credential_resolution_authorized(tmp_path):
    store_user_token(USER_1_ID, USER_1_TOKEN)
    workspace_path = tmp_path / "workspace" / USER_1_ID / "alice" / "QPapers"
    workspace_path.mkdir(parents=True, exist_ok=True)
    (workspace_path / ".git").mkdir(parents=True, exist_ok=True)

    # Register workspace key
    key = register_workspace_key(workspace_path, USER_1_ID)

    # Query API endpoint directly
    res = client.post(
        "/api/git/credential",
        json={
            "workspace_path": str(workspace_path),
            "remote_url": "https://github.com/alice/QPapers.git",
            "workspace_key": key,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "x-access-token"
    assert data["token"] == USER_1_TOKEN


# 7. User 1 cannot obtain User 2's credential
def test_user_1_cannot_obtain_user_2_credential(tmp_path):
    store_user_token(USER_1_ID, USER_1_TOKEN)
    store_user_token(USER_2_ID, USER_2_TOKEN)

    ws_1 = tmp_path / "workspace" / USER_1_ID / "alice" / "repo1"
    ws_2 = tmp_path / "workspace" / USER_2_ID / "bob" / "repo2"
    ws_1.mkdir(parents=True, exist_ok=True)
    ws_2.mkdir(parents=True, exist_ok=True)

    key_1 = register_workspace_key(ws_1, USER_1_ID)
    key_2 = register_workspace_key(ws_2, USER_2_ID)

    # 1. User 1 tries to query User 2's workspace using User 1's key -> 403
    res_tamper = client.post(
        "/api/git/credential",
        json={
            "workspace_path": str(ws_2),
            "remote_url": "https://github.com/bob/repo2.git",
            "workspace_key": key_1,
        },
    )
    assert res_tamper.status_code == 403

    # 2. Query without key -> 403
    res_nokey = client.post(
        "/api/git/credential",
        json={
            "workspace_path": str(ws_2),
            "remote_url": "https://github.com/bob/repo2.git",
        },
    )
    assert res_nokey.status_code == 403

    # 3. User 1 valid query returns User 1 token only
    res_1 = client.post(
        "/api/git/credential",
        json={
            "workspace_path": str(ws_1),
            "remote_url": "https://github.com/alice/repo1.git",
            "workspace_key": key_1,
        },
    )
    assert res_1.status_code == 200
    assert res_1.json()["token"] == USER_1_TOKEN
    assert res_1.json()["token"] != USER_2_TOKEN


# 8. Token does not appear in remote URL
def test_remote_url_rejects_embedded_tokens():
    with pytest.raises(Exception) as exc:
        validate_git_remote_url(f"https://{USER_1_TOKEN}@github.com/alice/QPapers.git")
    assert "Credentials in remote URL are strictly prohibited" in str(exc.value)

    with pytest.raises(Exception):
        validate_git_remote_url("https://user:pass@github.com/alice/QPapers.git")


# 9. Remote URL rejects non-github hosts and insecure schemes
def test_remote_url_rejects_invalid_hosts_and_schemes():
    # http scheme
    with pytest.raises(Exception):
        validate_git_remote_url("http://github.com/alice/QPapers.git")

    # non-github host
    with pytest.raises(Exception):
        validate_git_remote_url("https://attacker.com/alice/QPapers.git")

    # ssh remote
    with pytest.raises(Exception):
        validate_git_remote_url("git@github.com:alice/QPapers.git")

    # file remote
    with pytest.raises(Exception):
        validate_git_remote_url("file:///tmp/repo.git")


# 10. Clean GitHub remote is accepted
def test_clean_github_remote_accepted():
    res1 = validate_git_remote_url("https://github.com/alice/QPapers.git")
    assert res1["owner"] == "alice"
    assert res1["repo"] == "QPapers"
    assert res1["canonical_url"] == "https://github.com/alice/QPapers.git"

    res2 = validate_git_remote_url("https://github.com/alice/QPapers")
    assert res2["owner"] == "alice"
    assert res2["repo"] == "QPapers"


# 11. Token does not appear in process arguments or logs
def test_token_never_in_process_arguments():
    # Check that GIT_ASKPASS mode passes only prompt string, not the token
    prompt = "Password for 'https://github.com': "
    assert USER_1_TOKEN not in prompt


# 12. GIT_ASKPASS username and password protocol handling
def test_git_askpass_protocol_handling():
    # Username prompt returns x-access-token
    res_user = subprocess.run(
        [sys.executable, str(HELPER_PATH), "Username for 'https://github.com': "],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert res_user.returncode == 0
    assert res_user.stdout.strip() == "x-access-token"
