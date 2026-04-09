"""Jira project tools."""

from .app import mcp
from .client import jira_request


@mcp.tool()
async def get_issue_types(project_key: str) -> str:
    """Get available issue types for a Jira project.

    Args:
        project_key: Jira project key (e.g. PROJ)
    """
    data = await jira_request(
        "GET", f"/rest/api/3/issue/createmeta/{project_key}/issuetypes"
    )
    if isinstance(data, dict) and data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    issue_types = data.get("issueTypes") or data.get("values", [])
    if not issue_types:
        return f"No issue types found for project {project_key}"

    lines = [f"Issue types for {project_key}:\n"]
    for it in issue_types:
        name = it.get("name", "?")
        it_id = it.get("id", "?")
        subtask = it.get("subtask", False)
        description = it.get("description", "")
        tag = " [subtask]" if subtask else ""
        desc = f" - {description}" if description else ""
        lines.append(f"- [{it_id}] {name}{tag}{desc}")
    return "\n".join(lines)
