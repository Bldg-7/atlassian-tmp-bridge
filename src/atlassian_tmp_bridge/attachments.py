"""Jira attachment tools."""

import os

from mcp.server.fastmcp import Image

from .app import mcp
from .client import jira_get_binary, jira_request, jira_upload


@mcp.tool()
async def list_attachments(issue_key: str) -> str:
    """List all attachments for a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
    """
    data = await jira_request(
        "GET", f"/rest/api/3/issue/{issue_key}", params={"fields": "attachment"}
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

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
    # Fetch metadata for mime type
    meta = await jira_request("GET", f"/rest/api/3/attachment/{attachment_id}")
    if meta.get("error"):
        raise ValueError(f"Error: {meta['status']} - {meta['detail']}")
    mime_type = meta.get("mimeType", "application/octet-stream")

    # Download binary content
    content, _ = await jira_get_binary(f"/rest/api/3/attachment/content/{attachment_id}")

    fmt = mime_type.split("/")[-1] if "/" in mime_type else "png"
    return Image(data=content, format=fmt)


@mcp.tool()
async def upload_attachment(issue_key: str, file_path: str) -> str:
    """Upload a file as an attachment to a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
        file_path: Absolute path to the file to upload
    """
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()

    # Guess content type from extension
    ext_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".json": "application/json",
    }
    ext = os.path.splitext(filename)[1].lower()
    content_type = ext_map.get(ext, "application/octet-stream")

    data = await jira_upload(
        f"/rest/api/3/issue/{issue_key}/attachments",
        filename,
        file_data,
        content_type,
    )
    if isinstance(data, dict) and data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    if isinstance(data, list) and data:
        att = data[0]
        return f"Uploaded \"{att['filename']}\" to {issue_key} (attachment ID: {att['id']})"
    return f"Uploaded \"{filename}\" to {issue_key}"
