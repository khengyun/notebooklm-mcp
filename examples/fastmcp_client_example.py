#!/usr/bin/env python3
"""
FastMCP v2 HTTP Client Example
Demonstrates how to connect to NotebookLM FastMCP server via HTTP
"""

import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


async def main():
    """Example of using FastMCP v2 HTTP client"""
    print("🌐 FastMCP v2 HTTP Client Example")
    print("=" * 50)
    
    # Create HTTP transport
    transport = StreamableHttpTransport(
        url="http://localhost:8001/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json"
        }
    )
    
    try:
        # Connect to server
        async with Client(transport) as client:
            print("✅ Connected to FastMCP v2 server!")
            
            # List available tools
            tools = await client.list_tools()
            print(f"\n📋 Available tools ({len(tools)}):")
            for tool in tools[:3]:
                print(f"  • {tool.name}: {tool.description}")
            
            # Test healthcheck
            print("\n🔍 Testing healthcheck...")
            result = await client.call_tool("healthcheck", {})
            health_data = result.data
            print(f"  Status: {health_data['status']}")
            print(f"  Authenticated: {health_data['authenticated']}")
            
            # Send a message
            print("\n💬 Sending message to NotebookLM...")
            message_result = await client.call_tool("send_chat_message", {
                "request": {
                    "message": "Hello from FastMCP v2 client!",
                    "wait_for_response": False
                }
            })
            print(f"  Result: {message_result.data['status']}")
            
            print("\n🎉 Example completed successfully!")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure server is running:")
        print("notebooklm-mcp --config notebooklm-config.json server --transport http --port 8001 --headless")


if __name__ == "__main__":
    asyncio.run(main())