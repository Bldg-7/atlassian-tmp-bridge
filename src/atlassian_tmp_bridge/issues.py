"""Jira issue tools."""

from .adf import adf_to_text, text_to_adf
from .app import mcp
from .client import jira_request

DEFAULT_FIELDS = "summary,status,assignee,reporter,priority,labels,description,issuetype,created,updated,issuelinks,parent,subtasks"


KNOWN_FIELDS = {
    "summary", "status", "assignee", "reporter", "priority", "labels",
    "description", "issuetype", "created", "updated", "issuelinks",
    "parent", "subtasks",
}


def _format_custom_value(value: object) -> str:
    """Format a custom field value to a readable string."""
    if value is None:
        return "None"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_format_custom_value(item) for item in value]
        return ", ".join(parts)
    if isinstance(value, dict):
        # ADF document
        if value.get("type") == "doc" and "content" in value:
            return adf_to_text(value)
        # Common Jira object patterns
        if "name" in value:
            return value["name"]
        if "displayName" in value:
            return value["displayName"]
        if "value" in value:
            return str(value["value"])
        return str(value)
    return str(value)


def _format_issue(issue: dict) -> str:
    key = issue["key"]
    f = issue.get("fields", {})

    summary = f.get("summary", "")
    status = (f.get("status") or {}).get("name", "?")
    issue_type = (f.get("issuetype") or {}).get("name", "?")
    priority = (f.get("priority") or {}).get("name", "?")
    assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
    reporter = (f.get("reporter") or {}).get("displayName", "?")
    labels = ", ".join(f.get("labels", [])) or "None"
    created = (f.get("created") or "")[:10]
    updated = (f.get("updated") or "")[:10]
    description = adf_to_text(f.get("description"))

    lines = [
        f"[{key}] {summary}",
        f"Type: {issue_type} | Status: {status} | Priority: {priority}",
        f"Assignee: {assignee} | Reporter: {reporter}",
        f"Labels: {labels}",
        f"Created: {created} | Updated: {updated}",
    ]

    parent = f.get("parent")
    if parent:
        p_key = parent.get("key", "")
        p_summary = (parent.get("fields") or {}).get("summary", "")
        lines.append(f"Parent: [{p_key}] {p_summary}")

    subtasks = f.get("subtasks") or []
    if subtasks:
        lines.append("Subtasks:")
        for st in subtasks:
            st_key = st.get("key", "")
            st_fields = st.get("fields") or {}
            st_summary = st_fields.get("summary", "")
            st_status = (st_fields.get("status") or {}).get("name", "?")
            lines.append(f"  - [{st_key}] {st_summary} ({st_status})")

    links = f.get("issuelinks") or []
    if links:
        lines.append("Linked issues:")
        for link in links:
            link_type = link.get("type") or {}
            if "outwardIssue" in link:
                direction = link_type.get("outward", "relates to")
                other = link["outwardIssue"]
            elif "inwardIssue" in link:
                direction = link_type.get("inward", "relates to")
                other = link["inwardIssue"]
            else:
                continue
            o_key = other.get("key", "")
            o_fields = other.get("fields") or {}
            o_summary = o_fields.get("summary", "")
            o_status = (o_fields.get("status") or {}).get("name", "?")
            link_id = link.get("id", "")
            lines.append(f"  - (link_id={link_id}) {direction} [{o_key}] {o_summary} ({o_status})")

    # Custom / extra fields
    extra = {k: v for k, v in f.items() if k not in KNOWN_FIELDS and v is not None}
    if extra:
        lines.append("\nCustom fields:")
        for field_name, value in extra.items():
            lines.append(f"  {field_name}: {_format_custom_value(value)}")

    if description:
        lines.append(f"\nDescription:\n{description}")
    return "\n".join(lines)


def _format_issue_row(issue: dict) -> str:
    key = issue["key"]
    f = issue.get("fields", {})
    summary = f.get("summary", "")
    status = (f.get("status") or {}).get("name", "?")
    assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
    priority = (f.get("priority") or {}).get("name", "?")
    return f"- [{key}] {summary} | {status} | {assignee} | {priority}"


@mcp.tool()
async def get_issue(issue_key: str, fields: str = DEFAULT_FIELDS) -> str:
    """Get detailed information for a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
        fields: Comma-separated field names (default: core fields)
    """
    data = await jira_request("GET", f"/rest/api/3/issue/{issue_key}", params={"fields": fields})
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return _format_issue(data)


@mcp.tool()
async def count_issues(jql: str) -> str:
    """Count the approximate number of issues matching a JQL query.

    Args:
        jql: JQL query string (e.g. 'project = PROJ AND status = "In Progress"')
    """
    data = await jira_request(
        "POST",
        "/rest/api/3/search/approximate-count",
        json={"jql": jql},
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    count = data.get("count", 0)
    return f"Approximate count: {count}"


@mcp.tool()
async def search_issues(jql: str, max_results: int = 20, next_page_token: str = "") -> str:
    """Search Jira issues using JQL.

    Args:
        jql: JQL query string (e.g. 'project = PROJ AND status = "In Progress"')
        max_results: Maximum number of results per page (default 20, max 50)
        next_page_token: Token for fetching the next page (from previous search result)
    """
    max_results = min(max_results, 50)
    body: dict = {
        "jql": jql,
        "maxResults": max_results,
        "fields": ["summary", "status", "assignee", "priority"],
    }
    if next_page_token:
        body["nextPageToken"] = next_page_token

    data = await jira_request("POST", "/rest/api/3/search/jql", json=body)
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    issues = data.get("issues", [])
    if not issues:
        return "No results found"

    lines = [f"Search results ({len(issues)} shown):"]
    for issue in issues:
        lines.append(_format_issue_row(issue))

    token = data.get("nextPageToken")
    if token:
        lines.append(f"\nNext page token: {token}")

    return "\n".join(lines)


@mcp.tool()
async def create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
    assignee: str = "",
    priority: str = "",
    labels: str = "",
    parent_key: str = "",
) -> str:
    """Create a new Jira issue. Also used to create subtasks by specifying parent_key.

    Args:
        project_key: Project key (e.g. PROJ)
        summary: Issue title
        issue_type: Issue type name (default: Task). Use a subtask type (e.g. Sub-task) when creating subtasks.
        description: Issue description (plain text)
        assignee: Assignee account ID
        priority: Priority name (e.g. High, Medium, Low)
        labels: Comma-separated labels
        parent_key: Parent issue key for creating subtasks (e.g. PROJ-123)
    """
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if description:
        fields["description"] = text_to_adf(description)
    if assignee:
        fields["assignee"] = {"accountId": assignee}
    if priority:
        fields["priority"] = {"name": priority}
    if labels:
        fields["labels"] = [l.strip() for l in labels.split(",")]

    data = await jira_request("POST", "/rest/api/3/issue", json={"fields": fields})
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Created [{data['key']}] \"{summary}\""


@mcp.tool()
async def update_issue(
    issue_key: str,
    summary: str = "",
    description: str = "",
    assignee: str = "",
    priority: str = "",
    labels: str = "",
) -> str:
    """Update fields on an existing Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
        summary: New summary (leave empty to skip)
        description: New description in plain text (leave empty to skip)
        assignee: New assignee account ID (leave empty to skip)
        priority: New priority name (leave empty to skip)
        labels: Comma-separated labels (leave empty to skip)
    """
    fields: dict = {}
    if summary:
        fields["summary"] = summary
    if description:
        fields["description"] = text_to_adf(description)
    if assignee:
        fields["assignee"] = {"accountId": assignee}
    if priority:
        fields["priority"] = {"name": priority}
    if labels:
        fields["labels"] = [l.strip() for l in labels.split(",")]

    if not fields:
        return "Error: No fields to update"

    data = await jira_request("PUT", f"/rest/api/3/issue/{issue_key}", json={"fields": fields})
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Updated [{issue_key}]"


@mcp.tool()
async def delete_issue(issue_key: str) -> str:
    """Delete a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
    """
    data = await jira_request("DELETE", f"/rest/api/3/issue/{issue_key}")
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Deleted [{issue_key}]"
