"""Jira issue link tools."""

from .app import mcp
from .client import jira_request


@mcp.tool()
async def get_link_types() -> str:
    """Get all available issue link types (e.g. Blocks, Duplicate, Relates)."""
    data = await jira_request("GET", "/rest/api/3/issueLinkType")
    if isinstance(data, dict) and data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    link_types = data.get("issueLinkTypes", [])
    if not link_types:
        return "No link types found"

    lines = ["Available link types:\n"]
    for lt in link_types:
        lines.append(f"- [{lt['id']}] {lt['name']} (outward: \"{lt['outward']}\", inward: \"{lt['inward']}\")")
    return "\n".join(lines)


@mcp.tool()
async def link_issues(
    outward_issue_key: str,
    inward_issue_key: str,
    link_type: str = "Relates",
) -> str:
    """Create a link between two Jira issues.

    Args:
        outward_issue_key: The issue that performs the action (e.g. PROJ-1 "blocks" PROJ-2)
        inward_issue_key: The issue that receives the action (e.g. PROJ-2 "is blocked by" PROJ-1)
        link_type: Link type name (e.g. Blocks, Duplicate, Relates). Use get_link_types to see available types.
    """
    body = {
        "type": {"name": link_type},
        "outwardIssue": {"key": outward_issue_key},
        "inwardIssue": {"key": inward_issue_key},
    }

    data = await jira_request("POST", "/rest/api/3/issueLink", json=body)
    if isinstance(data, dict) and data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Linked {outward_issue_key} —[{link_type}]→ {inward_issue_key}"


@mcp.tool()
async def delete_link(link_id: str) -> str:
    """Delete an issue link.

    Args:
        link_id: Link ID (from issuelinks field on an issue)
    """
    data = await jira_request("DELETE", f"/rest/api/3/issueLink/{link_id}")
    if isinstance(data, dict) and data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Deleted link {link_id}"
