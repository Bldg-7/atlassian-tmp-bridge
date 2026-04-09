"""Jira MCP server — tool registration and entry point."""

from .app import mcp  # noqa: F401

# Import tool modules to trigger @mcp.tool() registration
import atlassian_tmp_bridge.issues  # noqa: F401
import atlassian_tmp_bridge.comments  # noqa: F401
import atlassian_tmp_bridge.attachments  # noqa: F401
import atlassian_tmp_bridge.transitions  # noqa: F401
import atlassian_tmp_bridge.bulk  # noqa: F401
import atlassian_tmp_bridge.projects  # noqa: F401


async def serve():
    await mcp.run_stdio_async()
