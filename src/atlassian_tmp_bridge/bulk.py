"""Jira bulk operation tools."""

import asyncio
import json

from .adf import text_to_adf
from .app import mcp
from .client import jira_request


@mcp.tool()
async def bulk_create_issues(project_key: str, issue_type: str, items: str) -> str:
    """Create multiple Jira issues at once (max 50).

    Args:
        project_key: Project key (e.g. PROJ)
        issue_type: Issue type name (e.g. Task, Bug, Story)
        items: JSON array of objects with at least "summary". Optional: "description", "priority", "labels", "assignee".
               Example: [{"summary": "Task 1"}, {"summary": "Task 2", "priority": "High"}]
    """
    try:
        item_list = json.loads(items)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON - {e}"

    if not isinstance(item_list, list) or not item_list:
        return "Error: items must be a non-empty JSON array"

    if len(item_list) > 50:
        return "Error: Maximum 50 issues per bulk create"

    issue_updates = []
    for item in item_list:
        fields: dict = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": item["summary"],
        }
        if item.get("description"):
            fields["description"] = text_to_adf(item["description"])
        if item.get("priority"):
            fields["priority"] = {"name": item["priority"]}
        if item.get("labels"):
            fields["labels"] = item["labels"] if isinstance(item["labels"], list) else [item["labels"]]
        if item.get("assignee"):
            fields["assignee"] = {"accountId": item["assignee"]}
        issue_updates.append({"fields": fields})

    data = await jira_request(
        "POST", "/rest/api/3/issue/bulk", json={"issueUpdates": issue_updates}
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    created = data.get("issues", [])
    errors = data.get("errors", [])

    lines = [f"Created {len(created)} issues:"]
    for issue in created:
        lines.append(f"- [{issue['key']}]")
    if errors:
        lines.append(f"\nErrors ({len(errors)}):")
        for err in errors:
            lines.append(f"- {err}")
    return "\n".join(lines)


@mcp.tool()
async def bulk_update_issues(updates: str) -> str:
    """Update multiple Jira issues in parallel.

    Args:
        updates: JSON array of objects with "key" and fields to update.
                 Example: [{"key": "PROJ-1", "summary": "New title"}, {"key": "PROJ-2", "priority": "High"}]
    """
    try:
        update_list = json.loads(updates)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON - {e}"

    if not isinstance(update_list, list) or not update_list:
        return "Error: updates must be a non-empty JSON array"

    async def _update_one(item: dict) -> tuple[str, bool, str]:
        key = item.get("key", "?")
        fields: dict = {}
        if item.get("summary"):
            fields["summary"] = item["summary"]
        if item.get("description"):
            fields["description"] = text_to_adf(item["description"])
        if item.get("assignee"):
            fields["assignee"] = {"accountId": item["assignee"]}
        if item.get("priority"):
            fields["priority"] = {"name": item["priority"]}
        if item.get("labels"):
            fields["labels"] = item["labels"] if isinstance(item["labels"], list) else [item["labels"]]

        if not fields:
            return key, False, "no fields to update"

        data = await jira_request("PUT", f"/rest/api/3/issue/{key}", json={"fields": fields})
        if data.get("error"):
            return key, False, f"{data['status']} - {data['detail']}"
        return key, True, ""

    results = await asyncio.gather(*[_update_one(item) for item in update_list])

    success = [(k, msg) for k, ok, msg in results if ok]
    failed = [(k, msg) for k, ok, msg in results if not ok]

    lines = [f"Updated {len(success)} / {len(results)} issues:"]
    for key, _ in success:
        lines.append(f"- [{key}] ✅")
    if failed:
        for key, msg in failed:
            lines.append(f"- [{key}] ❌ {msg}")
    return "\n".join(lines)
