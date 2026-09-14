import logging
from typing import Optional, Dict, Any
import httpx
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger("cloud_ide.deployments.render")

RENDER_API_BASE = "https://api.render.com/v1"


def normalize_status(render_status: Optional[str]) -> str:
    """
    Normalizes Render deployment statuses into Cloud IDE standard status codes:
    'in_progress', 'live', 'build_failed', 'canceled', or 'unknown'.
    """
    if not render_status:
        return "unknown"

    status = render_status.strip().lower()

    if status in (
        "created",
        "queued",
        "building",
        "build_in_progress",
        "update_in_progress",
        "pre_deploy_in_progress",
        "deploying",
    ):
        return "in_progress"

    if status == "live":
        return "live"

    if status in (
        "build_failed",
        "update_failed",
        "pre_deploy_failed",
        "failed",
    ):
        return "build_failed"

    if status in ("canceled", "cancelled", "deactivated"):
        return "canceled"

    return "unknown"


def _get_headers() -> Dict[str, str]:
    """Builds authorization and content headers for Render API."""
    api_key = settings.RENDER_API_KEY.strip()
    if not api_key:
        logger.error("Render API key is not configured in settings.")
        raise HTTPException(
            status_code=500,
            detail="Render authentication is unavailable.",
        )

    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def trigger_deployment(
    service_id: str,
    commit_id: str,
    clear_cache: str = "do_not_clear",
) -> Dict[str, Any]:
    """
    Triggers a new deployment on Render using the exact commit SHA.
    clear_cache must be 'do_not_clear' or 'clear'.
    """
    if clear_cache not in ("clear", "do_not_clear"):
        clear_cache = "do_not_clear"

    endpoint = f"{RENDER_API_BASE}/services/{service_id}/deploys"
    payload = {
        "commitId": commit_id.strip(),
        "clearCache": clear_cache,
    }

    headers = _get_headers()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error(f"Network failure contacting Render API: {type(exc).__name__}")
        raise HTTPException(status_code=502, detail="Unable to contact Render.")
    except Exception as exc:
        logger.error(f"Unexpected error communicating with Render API: {type(exc).__name__}")
        raise HTTPException(status_code=502, detail="Unable to contact Render.")

    if resp.status_code in (200, 201):
        try:
            return resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="Render deployment failed.")

    if resp.status_code in (401, 403):
        logger.error(f"Render API authentication failure: {resp.status_code}")
        raise HTTPException(status_code=502, detail="Render authentication is unavailable.")

    if resp.status_code == 404:
        logger.warning(f"Render service {service_id} not found.")
        raise HTTPException(status_code=404, detail="Render service not found.")

    if resp.status_code == 429:
        logger.warning(f"Render API rate limit reached on deploy trigger.")
        raise HTTPException(
            status_code=429,
            detail="Render deployment request was rate limited. Please try again later.",
        )

    logger.error(f"Render deployment trigger failed with status {resp.status_code}")
    raise HTTPException(status_code=502, detail="Render deployment failed.")


async def get_deployment(service_id: str, deploy_id: str) -> Dict[str, Any]:
    """
    Retrieves the exact deployment status by deploy_id.
    """
    endpoint = f"{RENDER_API_BASE}/services/{service_id}/deploys/{deploy_id}"
    headers = _get_headers()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(endpoint, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error(f"Network failure fetching Render deployment: {type(exc).__name__}")
        raise HTTPException(status_code=502, detail="Unable to contact Render.")
    except Exception as exc:
        logger.error(f"Unexpected error fetching Render deployment: {type(exc).__name__}")
        raise HTTPException(status_code=502, detail="Unable to contact Render.")

    if resp.status_code == 200:
        return resp.json()

    if resp.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="Render authentication is unavailable.")

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Deployment not found.")

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Render deployment request was rate limited. Please try again later.",
        )

    raise HTTPException(status_code=502, detail="Render deployment failed.")


async def get_latest_deployment(service_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent deployment for the service.
    """
    endpoint = f"{RENDER_API_BASE}/services/{service_id}/deploys?limit=1"
    headers = _get_headers()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(endpoint, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(status_code=502, detail="Unable to contact Render.")
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to contact Render.")

    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
            # Render API can return item or {"deploy": item}
            if isinstance(item, dict) and "deploy" in item:
                return item["deploy"]
            return item
        return None

    if resp.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="Render authentication is unavailable.")

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Render deployment request was rate limited. Please try again later.",
        )

    return None


async def get_service_details(service_id: str) -> Dict[str, Any]:
    """
    Fetches service information, including the service's public live URL.
    """
    endpoint = f"{RENDER_API_BASE}/services/{service_id}"
    headers = _get_headers()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(endpoint, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(status_code=502, detail="Unable to contact Render.")
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to contact Render.")

    if resp.status_code == 200:
        return resp.json()

    if resp.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="Render authentication is unavailable.")

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Render deployment request was rate limited. Please try again later.",
        )

    return {}


def extract_live_url(service_data: Dict[str, Any]) -> Optional[str]:
    """
    Extracts the public HTTPS URL from Render service representation.
    Checks serviceDetails.url, url, or service.serviceDetails.url.
    """
    if not isinstance(service_data, dict):
        return None

    # Try top-level url
    url = service_data.get("url")
    if url and isinstance(url, str) and url.startswith("http"):
        return url

    # Try serviceDetails.url
    details = service_data.get("serviceDetails")
    if isinstance(details, dict):
        url = details.get("url")
        if url and isinstance(url, str) and url.startswith("http"):
            return url

    # Try service.serviceDetails.url or service.url
    svc = service_data.get("service")
    if isinstance(svc, dict):
        url = svc.get("url")
        if url and isinstance(url, str) and url.startswith("http"):
            return url
        details = svc.get("serviceDetails")
        if isinstance(details, dict):
            url = details.get("url")
            if url and isinstance(url, str) and url.startswith("http"):
                return url

    return None
