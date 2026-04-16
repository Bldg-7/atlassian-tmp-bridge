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


@mcp.tool()
async def get_fields(project_key: str, issue_type_id: str = "", custom_only: bool = True) -> str:
    """Get available fields for a Jira project, grouped by issue type.

    Use get_issue_types first to find issue type IDs, then optionally filter by one.

    Args:
        project_key: Jira project key (e.g. PROJ)
        issue_type_id: Specific issue type ID to query (omit to show all issue types)
        custom_only: If true, only return custom fields (default: true)
    """
    # Resolve issue type IDs to query
    if issue_type_id:
        type_ids = [issue_type_id]
    else:
        types_data = await jira_request(
            "GET", f"/rest/api/3/issue/createmeta/{project_key}/issuetypes"
        )
        if isinstance(types_data, dict) and types_data.get("error"):
            return f"Error: {types_data['status']} - {types_data['detail']}"
        type_list = types_data.get("issueTypes") or types_data.get("values", [])
        if not type_list:
            return f"No issue types found for project {project_key}"
        type_ids = [t["id"] for t in type_list]

    lines: list[str] = []
    for tid in type_ids:
        data = await jira_request(
            "GET",
            f"/rest/api/3/issue/createmeta/{project_key}/issuetypes/{tid}",
            params={"maxResults": 200},
        )
        if isinstance(data, dict) and data.get("error"):
            lines.append(f"Issue type {tid}: Error {data['status']}")
            continue

        fields = data.get("fields") or data.get("values", [])
        if custom_only:
            fields = [f for f in fields if str(f.get("fieldId", "")).startswith("customfield_")]

        if not fields:
            continue

        type_name = data.get("name") or tid
        lines.append(f"[{type_name}] (issue type id: {tid})")
        for f in fields:
            fid = f.get("fieldId", "?")
            name = f.get("name", "?")
            required = " [required]" if f.get("required") else ""
            schema = f.get("schema") or {}
            ftype = schema.get("custom", schema.get("type", ""))
            type_str = f" ({ftype})" if ftype else ""
            lines.append(f"  - {fid}: {name}{type_str}{required}")
        lines.append("")

    if not lines:
        label = "custom fields" if custom_only else "fields"
        return f"No {label} found for project {project_key}"
    header = f"{'Custom fields' if custom_only else 'Fields'} for {project_key}:\n"
    return header + "\n".join(lines)
