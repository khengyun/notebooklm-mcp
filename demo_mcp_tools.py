#!/usr/bin/env python3
"""
Demo MCP Server Tools cho AutoGen
"""

import asyncio
import sys
sys.path.insert(0, 'src')

from notebooklm_mcp.server import NotebookLMServer
from notebooklm_mcp.config import ServerConfig, AuthConfig

async def demo_mcp_tools():
    """Demo các MCP tools available cho AutoGen"""
    
    print("🚀 NotebookLM MCP Server - AutoGen Integration Demo")
    print("=" * 60)
    
    # Setup config
    auth_config = AuthConfig(
        profile_dir='./chrome_profile_notebooklm',
        use_persistent_session=True
    )
    
    config = ServerConfig(
        headless=True,
        default_notebook_id="4741957b-f358-48fb-a16a-da8d20797bc6",
        auth=auth_config
    )
    
    # Create server instance  
    server = NotebookLMServer(config)
    
    print("📋 Available MCP Tools for AutoGen:")
    print("-" * 40)
    
    # Get tools list
    tools = await server.server.list_tools()()
    
    for i, tool in enumerate(tools, 1):
        print(f"{i}. 🔧 {tool.name}")
        print(f"   📝 Description: {tool.description}")
        
        if hasattr(tool, 'inputSchema') and tool.inputSchema:
            if 'properties' in tool.inputSchema:
                params = list(tool.inputSchema['properties'].keys())
                print(f"   ⚙️  Parameters: {params}")
        print()
    
    print(f"✅ Total: {len(tools)} tools ready for AutoGen McpWorkbench")
    
    print("\n🎯 Usage in AutoGen:")
    print("-" * 20)
    print("1. Start MCP server:")
    print("   notebooklm-mcp server --notebook YOUR_ID --headless")
    print()
    print("2. Connect from AutoGen McpWorkbench:")
    print("   - Transport: STDIO")
    print("   - Command: notebooklm-mcp server --notebook YOUR_ID --headless")
    print()
    print("3. Available operations:")
    for tool in tools:
        print(f"   - {tool.name}()")
    
    print("\n💡 Example AutoGen workflow:")
    print("```python")
    print("# In AutoGen agent")
    print("response = mcp_client.call_tool('chat_with_notebook', {")
    print("    'message': 'Explain MoE architecture'")
    print("})")
    print("```")

if __name__ == "__main__":
    asyncio.run(demo_mcp_tools())