from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # GitHub OAuth configuration
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: Optional[str] = None
    # Temporary classic OAuth scope to access user's private repos in Step 7.
    # When migrated to fine-grained GitHub Apps in future steps, replace with least-privilege repository permissions.
    GITHUB_OAUTH_SCOPES: str = "repo,read:user"

    # Two-user security model
    ALLOWED_GITHUB_USER_1: str = ""
    ALLOWED_GITHUB_USER_2: str = ""

    # Session configuration
    SESSION_SECRET: str = "dev-insecure-session-secret-change-in-production"
    SESSION_COOKIE_NAME: str = "cloudide_session"
    STATE_COOKIE_NAME: str = "cloudide_oauth_state"
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days
    STATE_MAX_AGE_SECONDS: int = 60 * 10  # 10 minutes

    # Environment
    ENVIRONMENT: str = "development"

    # Workspace directory root (defaults to /home/workspace on Linux/Render)
    WORKSPACE_ROOT: str = "/home/workspace"

    # Render API deployment configuration (Step 12)
    RENDER_API_KEY: str = ""
    # Map of "owner/repo": "service_id" in JSON or comma-separated pairs
    RENDER_SERVICE_MAP: str = "{}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def allowed_users(self) -> List[str]:
        """Returns list of configured allowed usernames/IDs in lowercase string format."""
        users = []
        if self.ALLOWED_GITHUB_USER_1.strip():
            users.append(self.ALLOWED_GITHUB_USER_1.strip().lower())
        if self.ALLOWED_GITHUB_USER_2.strip():
            users.append(self.ALLOWED_GITHUB_USER_2.strip().lower())
        return users

    def is_user_authorized(self, username: str, user_id: Optional[int | str] = None) -> bool:
        """
        Check if a GitHub user matches either of the two allowed slots.
        Matches against lowercase username and numeric user ID string.
        """
        if not self.allowed_users:
            return False

        normalized_username = username.strip().lower()
        if normalized_username in self.allowed_users:
            return True

        if user_id is not None and str(user_id).strip().lower() in self.allowed_users:
            return True

        return False

    def get_render_service_id(self, owner: str, repo: str) -> Optional[str]:
        """
        Resolves the configured Render service ID for a given repository (owner/repo).
        Returns None if not mapped.
        """
        import json
        key = f"{owner.strip()}/{repo.strip()}".lower()

        # Try JSON parsing first
        raw = self.RENDER_SERVICE_MAP.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                mapping = json.loads(raw)
                if isinstance(mapping, dict):
                    # Compare keys in lowercase
                    for map_key, srv_id in mapping.items():
                        if str(map_key).strip().lower() == key:
                            return str(srv_id).strip()
            except Exception:
                pass

        # Try comma-separated "owner/repo:srv-xxx,owner2/repo2:srv-yyy"
        if raw:
            for item in raw.split(","):
                item = item.strip()
                if ":" in item:
                    map_key, srv_id = item.split(":", 1)
                    if map_key.strip().lower() == key:
                        return srv_id.strip()

        return None


settings = Settings()

