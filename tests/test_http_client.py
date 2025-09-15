#!/usr/bin/env python3
"""
Test client for connecting to FastMCP v2 HTTP server
"""

import asyncio
import httpx
from typing import Dict, Any, Optional

class FastMCPHttpClient:
    """Simple HTTP client for testing FastMCP v2 server"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        self.base_url = base_url.rstrip('/')
        self.mcp_url = f"{self.base_url}/mcp"
        
    async def test_connection(self) -> Dict[str, Any]:
        """Test basic connection to the server"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health")
                return {
                    "status": "success",
                    "url": f"{self.base_url}/health",
                    "response": response.json() if response.status_code == 200 else response.text
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def list_tools(self) -> Dict[str, Any]:
        """List available MCP tools"""
        try:
            async with httpx.AsyncClient() as client:
                # MCP protocol: list tools
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {}
                }
                
                response = await client.post(
                    self.mcp_url,
                    json=mcp_request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                )
                
                return {
                    "status": "success",
                    "tools": response.json() if response.status_code == 200 else response.text,
                    "status_code": response.status_code
                }
        except Exception as e:
            return {
                "status": "error", 
                "error": str(e)
            }
    
    async def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call a specific MCP tool"""
        try:
            async with httpx.AsyncClient() as client:
                # MCP protocol: call tool
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments or {}
                    }
                }
                
                response = await client.post(
                    self.mcp_url,
                    json=mcp_request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                )
                
                return {
                    "status": "success",
                    "result": response.json() if response.status_code == 200 else response.text,
                    "status_code": response.status_code
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

async def test_fastmcp_http():
    """Test FastMCP v2 HTTP server"""
    
    print("🧪 Testing FastMCP v2 HTTP Server")
    print("=" * 50)
    
    client = FastMCPHttpClient()
    
    # Test 1: Basic connection
    print("\n1️⃣ Testing basic connection...")
    result = await client.test_connection()
    print(f"   Result: {result}")
    
    # Test 2: List tools
    print("\n2️⃣ Testing tools/list...")
    tools_result = await client.list_tools()
    print(f"   Status: {tools_result['status']}")
    print(f"   Status Code: {tools_result.get('status_code', 'N/A')}")
    if tools_result['status'] == 'success' and 'tools' in tools_result:
        tools = tools_result['tools']
        if isinstance(tools, dict) and 'result' in tools:
            tool_list = tools['result'].get('tools', [])
            print(f"   Found {len(tool_list)} tools:")
            for tool in tool_list[:3]:  # Show first 3
                print(f"     • {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')}")
    
    # Test 3: Call healthcheck tool
    print("\n3️⃣ Testing healthcheck tool...")
    health_result = await client.call_tool("healthcheck")
    print(f"   Status: {health_result['status']}")
    print(f"   Status Code: {health_result.get('status_code', 'N/A')}")
    if health_result['status'] == 'success':
        result = health_result.get('result', {})
        if isinstance(result, dict) and 'result' in result:
            health_data = result['result']
            print(f"   Health: {health_data}")
    
    # Test 4: Test send_chat_message
    print("\n4️⃣ Testing send_chat_message tool...")
    message_result = await client.call_tool("send_chat_message", {
        "message": "Hello from HTTP client!",
        "wait_for_response": False
    })
    print(f"   Status: {message_result['status']}")
    print(f"   Status Code: {message_result.get('status_code', 'N/A')}")
    if message_result['status'] == 'success':
        result = message_result.get('result', {})
        print(f"   Result: {result}")

def main():
    """Main test function"""
    print("🌐 FastMCP v2 HTTP Client Test")
    print("=" * 60)
    print("Make sure FastMCP server is running on http://127.0.0.1:8001")
    print("Command: notebooklm-mcp --config notebooklm-config.json server --fastmcp --transport http --port 8001 --headless")
    print()
    
    try:
        asyncio.run(test_fastmcp_http())
        print("\n✅ Test completed!")
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")

if __name__ == "__main__":
    main()