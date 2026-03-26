"""Shared Jira HTTP client."""

import base64
import os

import httpx

JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")


def _auth_header() -> str:
    credentials = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    return f"Basic {base64.b64encode(credentials.encode()).decode()}"


BASE_URL = f"https://{JIRA_DOMAIN}"
AUTH_HEADER = _auth_header()


async def jira_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: dict | list | None = None,
) -> dict:
    """Make a JSON API request to Jira. Returns parsed JSON or error dict."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": AUTH_HEADER, "Accept": "application/json"},
        timeout=30.0,
    ) as client:
        resp = await client.request(method, path, params=params, json=json)
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except Exception:
                err = resp.text
            return {"error": True, "status": resp.status_code, "detail": err}
        if resp.status_code == 204:
            return {}
        return resp.json()


async def jira_get_binary(path: str) -> tuple[bytes, str]:
    """Download binary content. Returns (bytes, content_type)."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": AUTH_HEADER, "Accept": "*/*"},
        timeout=60.0,
    ) as client:
        resp = await client.get(path, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "application/octet-stream")
        return resp.content, content_type


async def jira_upload(path: str, filename: str, data: bytes, content_type: str) -> dict:
    """Upload a file via multipart form data."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={
            "Authorization": AUTH_HEADER,
            "X-Atlassian-Token": "no-check",
        },
        timeout=60.0,
    ) as client:
        resp = await client.post(
            path,
            files={"file": (filename, data, content_type)},
        )
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except Exception:
                err = resp.text
            return {"error": True, "status": resp.status_code, "detail": err}
        return resp.json()
