"""Jira attachment download MCP server."""

import base64
import os

import httpx
from mcp.server.fastmcp import FastMCP, Image

mcp = FastMCP("atlassian-tmp-bridge")

JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")


def _auth_header() -> str:
    credentials = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"https://{JIRA_DOMAIN}",
        headers={"Authorization": _auth_header(), "Accept": "application/json"},
        timeout=30.0,
    )


@mcp.tool()
async def list_attachments(issue_key: str) -> str:
    """List all attachments for a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
    """
    async with _client() as client:
        resp = await client.get(f"/rest/api/3/issue/{issue_key}?fields=attachment")
        resp.raise_for_status()
        data = resp.json()

    attachments = data.get("fields", {}).get("attachment", [])
    if not attachments:
        return f"No attachments found on {issue_key}"

    lines = [f"Attachments on {issue_key}:\n"]
    for att in attachments:
        lines.append(
            f"- [{att['id']}] {att['filename']} "
            f"({att.get('mimeType', 'unknown')}, {att.get('size', 0)} bytes)"
        )
    return "\n".join(lines)


@mcp.tool()
async def download_attachment(attachment_id: str) -> Image:
    """Download a Jira attachment and return it as an image.

    Args:
        attachment_id: Attachment ID from list_attachments
    """
    async with _client() as client:
        # Fetch metadata for mime type
        meta_resp = await client.get(f"/rest/api/3/attachment/{attachment_id}")
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        mime_type = meta.get("mimeType", "application/octet-stream")

        # Download binary content
        content_resp = await client.get(
            f"/rest/api/3/attachment/content/{attachment_id}",
            headers={"Accept": "*/*"},
            follow_redirects=True,
        )
        content_resp.raise_for_status()

    fmt = mime_type.split("/")[-1] if "/" in mime_type else "png"
    return Image(data=content_resp.content, format=fmt)


async def serve():
    await mcp.run_stdio_async()
