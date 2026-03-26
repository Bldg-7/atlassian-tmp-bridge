"""Jira transition tools."""

from .adf import text_to_adf
from .app import mcp
from .client import jira_request


@mcp.tool()
async def get_transitions(issue_key: str) -> str:
    """Get available status transitions for a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
    """
    data = await jira_request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    transitions = data.get("transitions", [])
    if not transitions:
        return f"No transitions available for {issue_key}"

    lines = [f"Available transitions for {issue_key}:\n"]
    for t in transitions:
        to_status = (t.get("to") or {}).get("name", "?")
        lines.append(f"- [{t['id']}] {t['name']} → {to_status}")
    return "\n".join(lines)


@mcp.tool()
async def transition_issue(issue_key: str, transition_id: str, comment: str = "") -> str:
    """Transition a Jira issue to a new status.

    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
        transition_id: Transition ID from get_transitions
        comment: Optional comment to add with the transition
    """
    body: dict = {"transition": {"id": transition_id}}
    if comment:
        body["update"] = {
            "comment": [{"add": {"body": text_to_adf(comment)}}]
        }

    data = await jira_request(
        "POST", f"/rest/api/3/issue/{issue_key}/transitions", json=body
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"
    return f"Transitioned {issue_key} (transition: {transition_id})"
