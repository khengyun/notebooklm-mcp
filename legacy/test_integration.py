import asyncio
import os

from typing import Optional

try:
    from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
except Exception:
    McpWorkbench = None  # type: ignore
    StdioServerParams = None  # type: ignore


async def main() -> int:
    if McpWorkbench is None:
        print("autogen-ext not installed; skipping integration test.")
        return 0

    cookies = os.environ.get("NOTEBOOKLM_COOKIES", "notebooklm-mcp/example_cookies.json")
    notebook = os.environ.get("NOTEBOOKLM_NOTEBOOK", "4741957b-f358-48fb-a16a-da8d20797bc6")

    params = StdioServerParams(
        command="python",
        args=[
            "notebooklm-mcp/notebooklm_mcp_server.py",
            "--cookies", cookies,
            "--notebook", notebook,
            "--headless", "--debug",
        ],
        read_timeout_seconds=60,
    )

    async with McpWorkbench(params) as mcp:
        tools = await mcp.tools()
        tool_names = [t.name for t in tools]
        print("Tools:", tool_names)

    # Call healthcheck
        result = await mcp.call_tool("healthcheck", {})
        print("healthcheck:", result)

    # Verify default notebook id is set
    current = await mcp.call_tool("get_default_notebook", {})
    print("default_notebook:", current)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
