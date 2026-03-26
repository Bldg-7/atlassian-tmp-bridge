"""Jira comment tools."""

from .adf import adf_to_text, text_to_adf
from .app import mcp
from .client import jira_request


def _format_comment(comment: dict) -> str:
    cid = comment["id"]
    author = (comment.get("author") or {}).get("displayName", "?")
    created = (comment.get("created") or "")[:16].replace("T", " ")
    body = adf_to_text(comment.get("body"))
    return f"[{cid}] {author} ({created}):\n{body}"


@mcp.tool()
async def get_comments(issue_key: str) -> str:
    """Get all comments on a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
    """
    data = await jira_request("GET", f"/rest/api/3/issue/{issue_key}/comment")
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    comments = data.get("comments", [])
    if not comments:
        return f"No comments on {issue_key}"

    lines = [f"Comments on {issue_key} ({len(comments)}):\n"]
    for c in comments:
        lines.append(_format_comment(c))
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def add_comment(issue_key: str, body: str) -> str:
    """Add a comment to a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
        body: Comment text (plain text)
    """
    data = await jira_request(
        "POST",
        f"/rest/api/3/issue/{issue_key}/comment",
        json={"body": text_to_adf(body)},
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Added comment [{data['id']}] to {issue_key}"


@mcp.tool()
async def update_comment(issue_key: str, comment_id: str, body: str) -> str:
    """Update an existing comment on a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
        comment_id: Comment ID from get_comments
        body: New comment text (plain text)
    """
    data = await jira_request(
        "PUT",
        f"/rest/api/3/issue/{issue_key}/comment/{comment_id}",
        json={"body": text_to_adf(body)},
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Updated comment [{comment_id}] on {issue_key}"


@mcp.tool()
async def delete_comment(issue_key: str, comment_id: str) -> str:
    """Delete a comment from a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
        comment_id: Comment ID from get_comments
    """
    data = await jira_request(
        "DELETE",
        f"/rest/api/3/issue/{issue_key}/comment/{comment_id}",
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Deleted comment [{comment_id}] from {issue_key}"
