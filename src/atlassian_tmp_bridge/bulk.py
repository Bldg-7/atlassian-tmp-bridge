"""Jira bulk operation tools."""

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
async def bulk_update_issues(
    issue_keys: str,
    priority_id: str = "",
    labels: str = "",
    label_action: str = "ADD",
    description: str = "",
    send_notification: bool = False,
) -> str:
    """Bulk update multiple Jira issues with the same field values (max 1000).

    Args:
        issue_keys: Comma-separated issue keys (e.g. "PROJ-1,PROJ-2,PROJ-3")
        priority_id: Priority ID to set on all issues (e.g. "1" for Highest)
        labels: Comma-separated labels (e.g. "bug,urgent")
        label_action: How to apply labels: ADD, REMOVE, or REPLACE (default ADD)
        description: New description for all issues (plain text)
        send_notification: Send email notification for changes (default false)
    """
    keys = [k.strip() for k in issue_keys.split(",") if k.strip()]
    if not keys:
        return "Error: No issue keys provided"
    if len(keys) > 1000:
        return "Error: Maximum 1000 issues per bulk update"

    selected_actions: list[str] = []
    edited_fields: dict = {}

    if priority_id:
        selected_actions.append("priority")
        edited_fields["priority"] = {"priorityId": priority_id}

    if labels:
        selected_actions.append("labels")
        label_list = [{"name": l.strip()} for l in labels.split(",") if l.strip()]
        edited_fields["labelsFields"] = [{
            "fieldId": "labels",
            "labels": label_list,
            "bulkEditMultiSelectFieldOption": label_action.upper(),
        }]

    if description:
        selected_actions.append("description")
        edited_fields["richTextFields"] = [{
            "fieldId": "description",
            "richText": {"adfValue": text_to_adf(description)},
        }]

    if not selected_actions:
        return "Error: No fields to update"

    data = await jira_request(
        "POST",
        "/rest/api/3/bulk/issues/fields",
        json={
            "selectedActions": selected_actions,
            "selectedIssueIdsOrKeys": keys,
            "sendBulkNotification": send_notification,
            "editedFieldsInput": edited_fields,
        },
    )
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    task_id = data.get("taskId", "?")
    return f"Bulk update submitted (taskId: {task_id}, {len(keys)} issues)"
