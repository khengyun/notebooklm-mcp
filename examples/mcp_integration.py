#!/usr/bin/env python3
"""
Example: MCP integration with AutoGen
"""

import asyncio
import os
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

async def main():
    """Example using MCP with AutoGen"""
    
    # Get notebook ID from environment
    notebook_id = os.getenv("NOTEBOOKLM_NOTEBOOK_ID", "your-notebook-id")
    
    # Configure MCP server
    params = StdioServerParams(
        command="python",
        args=[
            "-m", "notebooklm_mcp.server",
            "--notebook", notebook_id,
            "--headless",
            "--debug"
        ],
        read_timeout_seconds=60,
    )
    
    # Create workbench
    workbench = McpWorkbench(params)
    
    try:
        print("🚀 Starting MCP workbench...")
        await workbench.__aenter__()
        
        # List available tools
        print("📋 Available tools:")
        tools = await workbench.list_tools()
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")
        
        # Test healthcheck
        print("\n🏥 Health check:")
        health = await workbench.call_tool("healthcheck", {})
        print(f"  Status: {health}")
        
        # Send chat message
        print("\n💬 Sending chat message...")
        response = await workbench.call_tool("chat_with_notebook", {
            "message": "What are the main topics covered in this research?",
            "max_wait": 60
        })
        print(f"  Response: {response}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        await workbench.__aexit__(None, None, None)
        print("👋 MCP session closed")

if __name__ == "__main__":
    asyncio.run(main())