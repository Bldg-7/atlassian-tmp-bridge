"""Jira user tools."""

from .app import mcp
from .client import jira_request


def _format_user_row(user: dict) -> str:
    account_id = user.get("accountId", "?")
    display_name = user.get("displayName", "?")
    email = user.get("emailAddress", "")
    active = user.get("active", True)
    account_type = user.get("accountType", "")
    tail_parts = []
    if account_type and account_type != "atlassian":
        tail_parts.append(account_type)
    if not active:
        tail_parts.append("inactive")
    tail = f" [{', '.join(tail_parts)}]" if tail_parts else ""
    email_part = f" <{email}>" if email else ""
    return f"- {display_name}{email_part} | accountId: {account_id}{tail}"


async def resolve_account_id(value: str) -> str:
    """Resolve an assignee string to a Jira accountId.

    Accepts:
      - "me" → current authenticated user's accountId
      - "-1" → Jira's automatic-assignee sentinel (passed through)
      - anything else → returned unchanged (assumed to already be an accountId)

    Returns the resolved accountId, or raises RuntimeError on failure.
    """
    if value != "me":
        return value
    data = await jira_request("GET", "/rest/api/3/myself")
    if data.get("error"):
        raise RuntimeError(f"{data['status']} - {data['detail']}")
    account_id = data.get("accountId")
    if not account_id:
        raise RuntimeError("myself response missing accountId")
    return account_id


@mcp.tool()
async def get_myself() -> str:
    """Get the authenticated Jira user's accountId and profile.

    Use the returned accountId as the assignee value in create_issue / update_issue.
    """
    data = await jira_request("GET", "/rest/api/3/myself")
    if data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    account_id = data.get("accountId", "?")
    display_name = data.get("displayName", "?")
    email = data.get("emailAddress", "")
    timezone = data.get("timeZone", "")
    locale = data.get("locale", "")

    lines = [
        f"accountId: {account_id}",
        f"Display name: {display_name}",
    ]
    if email:
        lines.append(f"Email: {email}")
    if timezone:
        lines.append(f"Time zone: {timezone}")
    if locale:
        lines.append(f"Locale: {locale}")
    return "\n".join(lines)


@mcp.tool()
async def search_users(query: str, max_results: int = 20) -> str:
    """Search Jira users by email, display name, or username.

    Args:
        query: Search string — email address, display name, or partial match
        max_results: Maximum number of users to return (default 20, max 50)
    """
    max_results = min(max(max_results, 1), 50)
    data = await jira_request(
        "GET",
        "/rest/api/3/user/search",
        params={"query": query, "maxResults": max_results},
    )
    if isinstance(data, dict) and data.get("error"):
        return f"Error: {data['status']} - {data['detail']}"

    users = data if isinstance(data, list) else []
    if not users:
        return f"No users found for query: {query}"

    lines = [f"Users matching \"{query}\" ({len(users)} shown):"]
    for user in users:
        lines.append(_format_user_row(user))
    return "\n".join(lines)
