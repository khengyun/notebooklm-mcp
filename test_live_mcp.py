#!/usr/bin/env python3
"""
Test live MCP call để demo cho AutoGen
"""

import asyncio
import sys
sys.path.insert(0, 'src')

from notebooklm_mcp.server import NotebookLMServer
from notebooklm_mcp.config import ServerConfig, AuthConfig

async def test_live_mcp_call():
    """Test actual MCP call như AutoGen sẽ làm"""
    
    print("🧪 Live MCP Call Test - AutoGen Simulation")
    print("=" * 50)
    
    # Setup config giống như production
    auth_config = AuthConfig(
        profile_dir='./chrome_profile_notebooklm',
        use_persistent_session=True
    )
    
    config = ServerConfig(
        headless=True,
        default_notebook_id="4741957b-f358-48fb-a16a-da8d20797bc6",
        auth=auth_config,
        timeout=30
    )
    
    server = NotebookLMServer(config)
    
    try:
        print("🚀 Starting MCP server (like AutoGen would)...")
        
        # Initialize client connection 
        await server._ensure_client()
        print("✅ MCP server initialized")
        
        # Test 1: Healthcheck
        print("\n💓 Test 1: Healthcheck")
        health_result = await server._execute_tool("healthcheck", {})
        print(f"📋 Result: {health_result}")
        
        # Test 2: Get default notebook
        print("\n📖 Test 2: Get Default Notebook")
        notebook_result = await server._execute_tool("get_default_notebook", {})
        print(f"📋 Result: {notebook_result}")
        
        # Test 3: Send chat message (actual AI interaction!)
        print("\n💬 Test 3: Chat with NotebookLM (Real AI call)")
        chat_result = await server._execute_tool("chat_with_notebook", {
            "message": "What are the key benefits of MoE architecture?", 
            "max_wait": 25
        })
        print(f"📋 AI Response: {chat_result[:200]}..." if len(chat_result) > 200 else f"📋 AI Response: {chat_result}")
        
        print("\n🎯 All MCP tools working perfectly!")
        print("🚀 Ready for AutoGen McpWorkbench integration!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure Chrome profile with auth exists")
        
    finally:
        if server.client:
            await server.client.close()

if __name__ == "__main__":
    asyncio.run(test_live_mcp_call())